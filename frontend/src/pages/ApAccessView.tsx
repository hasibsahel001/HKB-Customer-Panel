import { useState } from 'react'
import { ApiError, api, toApiError } from '../api'
import type { ActionCustomer, NatEnterResult, VpnEnterResult } from '../actionTypes'
import { copyText } from '../clipboard'
import { ErrorBox, Modal, Spinner } from '../ui'

type NatState = 'added' | 'updated' | 'moved' | 'unchanged'

const NAT_NOTE: Record<NatState, (ap: string) => string> = {
  added: (ap) => `NAT rule added at the top of the list for ${ap}.`,
  updated: (ap) => `The existing port-90 NAT rule was changed to ${ap} and moved to the top.`,
  moved: (ap) => `The NAT rule for ${ap} was moved to the top of the list.`,
  unchanged: (ap) => `NAT rule for ${ap} was already in place.`,
}

/** What the panel did to the Windows VPN entry (it only does this on a Windows panel PC). */
interface LocalVpn {
  supported: boolean
  name?: string
  server?: string
  state?: 'created' | 'updated'
  connected?: boolean | null
  credentials_saved?: boolean
  message?: string | null
}

interface VpnShown extends VpnEnterResult {
  vpn: LocalVpn | null
}

function CopyChip({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    if (await copyText(value)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }
  return (
    <button className="copy-chip mono" onClick={() => void copy()} title="Click to copy">
      {value}
      <span className="copy-chip-tag">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  )
}

function VpnInfoModal({ info, onClose }: { info: VpnShown; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const vpn = info.vpn
  const name = vpn?.name ?? 'VPN'

  async function copy() {
    if (await copyText(info.pppoe_ip)) setCopied(true)
  }

  return (
    <Modal title="Local IP access" onClose={onClose}>
      {vpn?.supported && vpn.connected && (
        <div className="ok-box">
          The Windows VPN <strong>{name}</strong> was {vpn.state === 'created' ? 'created' : 'updated'} for this
          customer ({info.pppoe_ip}) and is connected. Open the access point at the address below.
        </div>
      )}
      {vpn?.supported && vpn.connected === null && (
        <div className="ok-box">
          The Windows VPN <strong>{name}</strong> was {vpn.state === 'created' ? 'created' : 'updated'} with this
          customer's address ({info.pppoe_ip}). Press <strong>Connect</strong> on it in Windows, then open the access
          point at the address below.
          {!vpn.credentials_saved && ' Windows did not keep the user name and password: enter 1 / 1 on the first connect.'}
        </div>
      )}
      {vpn?.supported && vpn.connected === false && (
        <div className="notice">
          The Windows VPN <strong>{name}</strong> was {vpn.state === 'created' ? 'created' : 'updated'} with this
          customer's address ({info.pppoe_ip}), but it did not connect by itself
          {vpn.message ? `: ${vpn.message}` : '.'} Connect it by hand in the Windows VPN list, then refresh the AP
          page.
        </div>
      )}
      {(!vpn || !vpn.supported) && (
        <>
          <p>
            PPTP access was confirmed on the router. {vpn?.message ?? 'The VPN could not be set up automatically.'}{' '}
            Use this PPPoE IP as the server address in the Windows VPN connection:
          </p>
          <div className="toolbar" style={{ margin: '10px 0' }}>
            <code className="mono" style={{ fontSize: 16 }}>
              {info.pppoe_ip}
            </code>
            <button className="btn secondary" onClick={() => void copy()}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </>
      )}
      <div className="ap-address">
        <span className="muted small">Access point address (click to copy)</span>
        <CopyChip value={info.ap_ip} />
      </div>
      <div className="muted small" style={{ marginTop: 10 }}>
        VPN user and password: <code className="mono">1</code> / <code className="mono">1</code> (created on the
        router for this connection).
      </div>
    </Modal>
  )
}

export function ApAccessView({ customer }: { customer: ActionCustomer }) {
  const [busy, setBusy] = useState<'nat' | 'vpn' | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [note, setNote] = useState('')
  const [vpnInfo, setVpnInfo] = useState<VpnShown | null>(null)
  const base = { ip: customer.ip, tid: customer.tid }

  async function enterViaNat() {
    setBusy('nat')
    setError(null)
    setNote('')
    try {
      const result = await api<NatEnterResult & { rule_state?: NatState }>('/api/router/manage/nat-enter', {
        method: 'POST',
        body: base,
      })
      window.open(`http://${result.pppoe_ip}:${result.port}`, '_blank', 'noopener,noreferrer')
      const state: NatState = result.rule_state ?? (result.rule_added ? 'added' : 'unchanged')
      setNote(`${NAT_NOTE[state](result.ap_ip)} Opened http://${result.pppoe_ip}:${result.port} in a new tab.`)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(null)
    }
  }

  async function enterViaLocalIp() {
    setBusy('vpn')
    setError(null)
    setNote('')
    try {
      const result = await api<VpnEnterResult>('/api/router/manage/vpn-enter', { method: 'POST', body: base })
      let vpn: LocalVpn | null = null
      try {
        vpn = await api<LocalVpn>('/api/router/manage/vpn-connect', {
          method: 'POST',
          body: { ip: result.pppoe_ip, ap_ip: result.ap_ip },
        })
      } catch (e) {
        setError(toApiError(e))
      }
      setVpnInfo({ ...result, vpn })
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <p className="muted small">
        Lets you reach this customer's own access point from outside their network. NAT opens the AP's admin page
        through the customer's PPPoE IP; Enter with VPN sets up the panel's fixed PPTP connection and shows the AP's
        local address to open after you connect. On a Windows panel PC it also creates or updates the Windows VPN named "VPN" (PPTP, user and
        password 1) with this customer's PPPoE IP; you only press Connect in Windows.
      </p>
      <ErrorBox error={error} />
      <div className="toolbar">
        <button className="btn secondary" disabled={busy !== null} onClick={() => void enterViaNat()}>
          {busy === 'nat' ? (
            <>
              <Spinner /> Entering via NAT…
            </>
          ) : (
            'Enter via NAT'
          )}
        </button>
        <button className="btn secondary" disabled={busy !== null} onClick={() => void enterViaLocalIp()}>
          {busy === 'vpn' ? (
            <>
              <Spinner /> Preparing the VPN…
            </>
          ) : (
            'Enter with VPN'
          )}
        </button>
      </div>
      {note && <div className="ok-box">{note}</div>}
      {vpnInfo && <VpnInfoModal info={vpnInfo} onClose={() => setVpnInfo(null)} />}
    </>
  )
}