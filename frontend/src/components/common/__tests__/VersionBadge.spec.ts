import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const { store } = vi.hoisted(() => ({ store: {
  versionLoading: false, currentVersion: 'opentv-73480acd737c',
  latestVersion: '0.2.15', hasUpdate: true, buildType: 'release',
  releaseInfo: { html_url: 'https://github.com/Wei-Shaw/sub2api/releases/tag/v0.2.15' },
  fetchVersion: vi.fn(), clearVersionCache: vi.fn()
} }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores', () => ({ useAuthStore: () => ({ isAdmin: true }), useAppStore: () => store }))
vi.mock('@/api/admin/system', () => ({ performUpdate: vi.fn(), restartService: vi.fn(), getRollbackVersions: vi.fn(), rollback: vi.fn() }))
vi.mock('@/composables/useClipboard', () => ({ useClipboard: () => ({ copied: false, copyToClipboard: vi.fn() }) }))
import VersionBadge from '../VersionBadge.vue'

describe('Custom image updates', () => {
  beforeEach(() => {
    store.currentVersion = 'opentv-73480acd737c'
    store.buildType = 'release'
  })
  it.each(['release', 'custom'])('protects fork builds with %s metadata', async (buildType) => {
    store.buildType = buildType
    const wrapper = mount(VersionBadge, { global: { stubs: { Icon: true } } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.find('[data-testid="custom-build-update"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('version.upstreamVersion')
    expect(wrapper.text()).not.toContain('version.updateAvailable')
    expect(wrapper.text()).not.toContain('version.upToDate')
    expect(wrapper.text()).not.toContain('version.updateNow')
    expect(wrapper.text()).not.toContain('version.rollback')
    expect(wrapper.find('a[href*="the-wayee/sub2api/actions"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('preserves the update button for official releases', async () => {
    store.currentVersion = '0.2.14'
    const wrapper = mount(VersionBadge, { global: { stubs: { Icon: true } } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.find('[data-testid="custom-build-update"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('version.updateNow')
    wrapper.unmount()
  })
})
