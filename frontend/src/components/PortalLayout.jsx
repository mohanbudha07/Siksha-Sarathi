import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined'
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined'
import QuizOutlinedIcon from '@mui/icons-material/QuizOutlined'
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined'
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined'
import EventAvailableOutlinedIcon from '@mui/icons-material/EventAvailableOutlined'
import CampaignOutlinedIcon from '@mui/icons-material/CampaignOutlined'
import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined'
import PeopleAltOutlinedIcon from '@mui/icons-material/PeopleAltOutlined'
import SchoolOutlinedIcon from '@mui/icons-material/SchoolOutlined'
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined'
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined'
import ScienceOutlinedIcon from '@mui/icons-material/ScienceOutlined'
import AssignmentOutlinedIcon from '@mui/icons-material/AssignmentOutlined'
import MenuRoundedIcon from '@mui/icons-material/MenuRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined'
import './PortalLayout.css'

const icons = {
  dashboard: DashboardOutlinedIcon,
  plan: EventNoteOutlinedIcon,
  quizzes: QuizOutlinedIcon,
  notes: MenuBookOutlinedIcon,
  ai: AutoAwesomeOutlinedIcon,
  attendance: EventAvailableOutlinedIcon,
  notices: CampaignOutlinedIcon,
  chat: ForumOutlinedIcon,
  users: PeopleAltOutlinedIcon,
  school: SchoolOutlinedIcon,
  csv: StorageOutlinedIcon,
  insights: InsightsOutlinedIcon,
  lab: ScienceOutlinedIcon,
  marks: AssignmentOutlinedIcon,
}

function PortalLayout({
  role,
  portalName,
  homePath,
  groups,
  unreadCount,
  onLogout,
  children,
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  return (
    <div className={`portal-shell portal-shell-${role}`}>
      {menuOpen && (
        <button
          className="portal-overlay"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`portal-sidebar ${menuOpen ? 'is-open' : ''}`} id="portal-navigation">
        <NavLink className="portal-brand" to={homePath} onClick={() => setMenuOpen(false)}>
          <span className="portal-brand-mark" aria-hidden="true">SS</span>
          <span className="portal-brand-copy">
            <strong>Siksha Sarathi</strong>
            <small>{portalName}</small>
          </span>
          <button
            className="portal-sidebar-close"
            type="button"
            aria-label="Close navigation"
            onClick={(event) => { event.preventDefault(); setMenuOpen(false) }}
          >
            <CloseRoundedIcon fontSize="small" />
          </button>
        </NavLink>

        <nav className="portal-navigation" aria-label={`${portalName} navigation`}>
          {groups.map((group) => (
            <section className="portal-nav-group" key={group.label}>
              <h2>{group.label}</h2>
              {group.items.map((item) => {
                const Icon = icons[item.icon]
                return (
                  <NavLink
                    className={({ isActive }) => `portal-nav-link${isActive ? ' is-active' : ''}`}
                    key={item.to}
                    to={item.to}
                    onClick={() => setMenuOpen(false)}
                  >
                    <span className="portal-nav-icon" aria-hidden="true"><Icon fontSize="small" /></span>
                    <span className="portal-nav-label">{item.label}</span>
                    {item.icon === 'notices' && unreadCount > 0 && (
                      <span className="portal-nav-badge" aria-label={`${unreadCount} unread notices`}>
                        {unreadCount}
                      </span>
                    )}
                  </NavLink>
                )
              })}
            </section>
          ))}
        </nav>

        <footer className="portal-sidebar-footer">
          <div className="portal-account-mark" aria-hidden="true">{role.slice(0, 1).toUpperCase()}</div>
          <div className="portal-account-copy"><strong>{portalName}</strong><small>Secure workspace</small></div>
          <button className="portal-logout" type="button" onClick={onLogout} aria-label="Log out">
            <LogoutOutlinedIcon fontSize="small" />
          </button>
        </footer>
      </aside>

      <div className="portal-main">
        <header className="portal-mobile-header">
          <button
            className="portal-menu-button"
            type="button"
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menuOpen}
            aria-controls="portal-navigation"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <CloseRoundedIcon /> : <MenuRoundedIcon />}
          </button>
          <div><strong>Siksha Sarathi</strong><span>{portalName}</span></div>
        </header>
        <main className="portal-content">{children}</main>
      </div>
    </div>
  )
}

export default PortalLayout
