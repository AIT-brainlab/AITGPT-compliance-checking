import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BookOpen, ShieldCheck, Play } from 'lucide-react'

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <h1>PolicyChecker</h1>
        <span>Compliance Dashboard</span>
      </div>
      <nav className="sidebar-nav">
        <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
          <LayoutDashboard /> Dashboard
        </NavLink>
        <NavLink to="/rules" className={({ isActive }) => isActive ? 'active' : ''}>
          <BookOpen /> Policy Rules
        </NavLink>
        <NavLink to="/validate" className={({ isActive }) => isActive ? 'active' : ''}>
          <ShieldCheck /> Validate
        </NavLink>
        <NavLink to="/pipeline" className={({ isActive }) => isActive ? 'active' : ''}>
          <Play /> Run Pipeline
        </NavLink>
      </nav>
      <div className="sidebar-footer">
        AIT Master's Thesis · 2026<br />
        v2.1-final-defense
      </div>
    </aside>
  )
}
