import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server

class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.config = {'secret':'private-secret','mixed-port':7890,'proxy-providers':{'subscription':{'type':'http','url':'https://example.com/token-secret','path':'./providers/subscription.yaml','interval':86400}},'proxy-groups':[{'name':'AI-PROXY','type':'select','use':['subscription']}], 'rules':['MATCH,AI-PROXY']}
        self.dns = patch.object(server.socket, 'getaddrinfo', return_value=[(2,1,6,'',('8.8.8.8',443))])
        self.dns.start()
        self.addCleanup(self.dns.stop)
    def test_add_rename_preserves_settings(self):
        original=copy.deepcopy(self.config)
        added=server.edit_config(self.config,'save',{'name':'第二订阅','url':'https://example.com/new'})
        self.assertEqual(self.config,original)
        self.assertEqual(added['secret'],'private-secret')
        self.assertEqual(added['rules'],original['rules'])
        self.assertEqual(added['proxy-groups'][0]['use'],['subscription','第二订阅'])
        renamed=server.edit_config(added,'save',{'original':'第二订阅','name':'新名称','url':''})
        self.assertEqual(renamed['proxy-groups'][0]['use'],['subscription','新名称'])
        self.assertEqual(renamed['proxy-providers']['新名称']['url'],'https://example.com/new')
        removed=server.edit_config(renamed,'delete',{'original':'新名称'})
        self.assertEqual(removed['proxy-groups'][0]['use'],['subscription'])
    def test_last_subscription_cannot_be_deleted(self):
        with self.assertRaises(ValueError): server.edit_config(self.config,'delete',{'original':'subscription'})
    def test_private_address_blocked(self):
        with patch.object(server.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError): server.validate_url('https://example.com/a')
    def test_reload_failure_restores_file_and_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.yaml'; path.write_text(json.dumps(self.config))
            old=path.read_bytes(); inode=path.stat().st_ino
            new=copy.deepcopy(self.config);new['mixed-port']=7891
            with patch.object(server,'CONFIG',path), patch.object(server.subprocess,'run') as run, patch.object(server,'core_request',side_effect=[RuntimeError(),{}]):
                run.return_value.returncode=0
                with self.assertRaises(RuntimeError): server.apply_config(self.config,new)
            self.assertEqual(path.read_bytes(),old)
            self.assertEqual(path.stat().st_ino,inode)
            self.assertEqual(len(list((Path(directory)/'subscription-backups').glob('*.json'))),1)
    def test_invalid_config_does_not_write(self):
        with patch.object(server.subprocess,'run') as run:
            run.return_value.returncode=1
            with self.assertRaises(ValueError): server.apply_config(self.config,self.config)

if __name__=='__main__': unittest.main()
