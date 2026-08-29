import { useState } from 'react'
import {
  fetchGroupMembers,
  inviteToGroup,
  removeGroupMember,
  cancelGroupInvite,
  renameGroup,
  changeMemberRole,
} from '../api/client.js'

const INVITE_ROLES = [
  { value: 'admin', label: 'Admin — can invite + manage expenses' },
  { value: 'editor', label: 'Editor — can add/edit expenses' },
  { value: 'viewer', label: 'Viewer — read only' },
]

const SPACE_TYPES = [
  { value: 'household', label: 'Household', icon: '🏠' },
  { value: 'business', label: 'Business', icon: '💼' },
  { value: 'rental', label: 'Rental', icon: '🏢' },
  { value: 'trip', label: 'Trip', icon: '✈️' },
  { value: 'custom', label: 'Custom', icon: '📁' },
]

function spaceTypeIcon(spaceType) {
  return SPACE_TYPES.find((t) => t.value === spaceType)?.icon || '📁'
}

export default function GroupsPage({ groups, onCreateGroup, onDeleteGroup, onLeaveGroup, onRefresh, onError }) {
  const [name, setName] = useState('')
  const [spaceType, setSpaceType] = useState('custom')
  const [expandedId, setExpandedId] = useState(null)
  const [members, setMembers] = useState([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('editor')
  const [loadingMembers, setLoadingMembers] = useState(false)

  async function handleCreate(e) {
    e.preventDefault()
    if (!name.trim()) return
    await onCreateGroup(name.trim(), spaceType)
    setName('')
    setSpaceType('custom')
  }

  async function loadMembers(groupId) {
    setLoadingMembers(true)
    try {
      setMembers(await fetchGroupMembers(groupId))
    } catch (err) {
      onError(err.message)
    } finally {
      setLoadingMembers(false)
    }
  }

  function toggleExpand(group) {
    if (expandedId === group.id) {
      setExpandedId(null)
      setMembers([])
      return
    }
    setExpandedId(group.id)
    setInviteEmail('')
    loadMembers(group.id)
  }

  async function handleInvite(e, groupId) {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    try {
      await inviteToGroup(groupId, inviteEmail.trim(), inviteRole)
      setInviteEmail('')
      await loadMembers(groupId)
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleRoleChange(groupId, userId, role) {
    try {
      await changeMemberRole(groupId, userId, role)
      await loadMembers(groupId)
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleRemove(groupId, userId) {
    try {
      await removeGroupMember(groupId, userId)
      await loadMembers(groupId)
      await onRefresh()
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleCancelInvite(groupId, email) {
    try {
      await cancelGroupInvite(groupId, email)
      await loadMembers(groupId)
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleRename(group) {
    const newName = window.prompt('Rename group', group.name)
    if (!newName || !newName.trim() || newName.trim() === group.name) return
    try {
      await renameGroup(group.id, newName.trim())
      await onRefresh()
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <>
      <h1 className="page-title">🗂️ Expense Spaces</h1>
      <p className="subtitle">
        An Expense Space is where expenses belong — a household, a business, a rental, a trip, or anything custom.
        Invite others to a space so every member can add expenses to it, all in one shared view.
      </p>

      <section className="panel">
        <h2>➕ New Expense Space</h2>
        <form className="add-form" onSubmit={handleCreate}>
          <input
            type="text"
            placeholder="e.g. Household, Business A, Goa Trip"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select value={spaceType} onChange={(e) => setSpaceType(e.target.value)} title="Space type">
            {SPACE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.icon} {t.label}
              </option>
            ))}
          </select>
          <button type="submit">Create</button>
        </form>
      </section>

      {groups.length === 0 ? (
        <p className="subtitle">No Expense Spaces yet — create one above to start sharing expenses with others.</p>
      ) : (
        <div className="trip-list">
          {groups.map((g) => (
            <section key={g.id} className="panel trip-card">
              <div className="trip-card-header" onClick={() => toggleExpand(g)}>
                <div>
                  <h2 style={{ margin: 0 }}>
                    {spaceTypeIcon(g.space_type)} {g.name}
                  </h2>
                  <p className="subtitle">
                    {g.space_type_label} · {g.member_count} member{g.member_count === 1 ? '' : 's'} ·{' '}
                    <span className={`role-badge role-${g.role}`}>{g.role}</span>
                  </p>
                </div>
                <div className="trip-card-actions" onClick={(e) => e.stopPropagation()}>
                  {g.role === 'owner' ? (
                    <>
                      <button className="ghost-btn" onClick={() => handleRename(g)}>
                        Rename
                      </button>
                      <button className="delete-btn" onClick={() => onDeleteGroup(g.id)} title="Delete space">
                        ✕
                      </button>
                    </>
                  ) : (
                    <button className="ghost-btn" onClick={() => onLeaveGroup(g.id)}>
                      Leave
                    </button>
                  )}
                </div>
              </div>

              {expandedId === g.id && (
                <div className="trip-detail">
                  {loadingMembers ? (
                    <p className="subtitle">Loading…</p>
                  ) : (
                    <>
                      <ul className="member-list">
                        {members.map((m) => (
                          <li key={m.user_id ?? m.email}>
                            <span>
                              {m.role === 'invited' ? '✉️' : '👤'} {m.name || m.email}
                              {m.role !== 'invited' && m.name ? ` (${m.email})` : ''}
                            </span>
                            {g.role === 'owner' && m.role !== 'owner' && m.role !== 'invited' ? (
                              <select value={m.role} onChange={(e) => handleRoleChange(g.id, m.user_id, e.target.value)}>
                                {INVITE_ROLES.map((r) => (
                                  <option key={r.value} value={r.value}>
                                    {r.value}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <span className={`role-badge role-${m.role}`}>{m.role}</span>
                            )}
                            {g.role === 'owner' && m.role !== 'owner' && m.role !== 'invited' && (
                              <button className="delete-btn" onClick={() => handleRemove(g.id, m.user_id)} title="Remove">
                                ✕
                              </button>
                            )}
                            {g.role === 'owner' && m.role === 'invited' && (
                              <button
                                className="delete-btn"
                                onClick={() => handleCancelInvite(g.id, m.email)}
                                title="Cancel invite"
                              >
                                ✕
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                      {g.role === 'owner' && (
                        <form className="add-form" onSubmit={(e) => handleInvite(e, g.id)}>
                          <input
                            type="email"
                            placeholder="Invite by email"
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                          />
                          <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                            {INVITE_ROLES.map((r) => (
                              <option key={r.value} value={r.value}>
                                {r.label}
                              </option>
                            ))}
                          </select>
                          <button type="submit">Invite</button>
                        </form>
                      )}
                    </>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </>
  )
}
