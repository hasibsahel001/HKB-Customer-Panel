import { describe, expect, it } from 'vitest'
import { deviceName, isPrivateMac } from './devices'

describe('isPrivateMac', () => {
  it('detects locally administered addresses', () => {
    expect(isPrivateMac('5E:41:4B:6A:9A:90')).toBe(true)
    expect(isPrivateMac('9E:26:4A:DA:82:38')).toBe(true)
  })
  it('keeps real vendor addresses as not private', () => {
    expect(isPrivateMac('00:08:22:A4:BA:DA')).toBe(false)
    expect(isPrivateMac('DC:10:57:30:99:94')).toBe(false)
  })
  it('handles garbage', () => {
    expect(isPrivateMac('')).toBe(false)
    expect(isPrivateMac('zz')).toBe(false)
  })
})

describe('deviceName', () => {
  it('prefers the hostname', () => {
    expect(deviceName('iPhone', '5E:41:4B:6A:9A:90')).toEqual({ text: 'iPhone', named: true })
  })
  it('labels unnamed devices without guessing a brand', () => {
    expect(deviceName(null, '5E:41:4B:6A:9A:90').text).toBe('IPhone')
    expect(deviceName(null, '00:08:22:A4:BA:DA').text).toBe('Unnamed device')
  })
})