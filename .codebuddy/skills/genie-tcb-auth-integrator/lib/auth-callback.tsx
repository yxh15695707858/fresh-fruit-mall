import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { signInWithOAuthProvider } from '../lib/cloudbase'

export default function AuthCallback() {
  const navigate = useNavigate()
  const handled = useRef(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (handled.current) return
    handled.current = true

    const handleCallback = async () => {
      const params = new URLSearchParams(window.location.search)
      const code = params.get('code')
      const state = params.get('state')
      const provider = params.get('provider') || 'google'
      const providerId = params.get('provider_id')
      const isPopup = params.get('mode') === 'popup'

      if (!code) {
        navigate('/')
        return
      }

      try {
        if (state && providerId) {
          await signInWithOAuthProvider(providerId, code, { state })
        } else {
          throw new Error(`Legacy ${provider} callback requires oauth-callback cloud function`)
        }

        if (isPopup && window.opener) {
          window.opener.postMessage(
            { type: 'oauth_callback', success: true },
            window.location.origin
          )
          window.close()
        } else {
          navigate('/dashboard')
        }
      } catch (err) {
        setError('Login failed')
        setTimeout(() => navigate('/'), 2000)
      }
    }

    handleCallback()
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: '1rem' }}>
      <div className="spinner" />
      <p>{error || 'Completing login...'}</p>
    </div>
  )
}
