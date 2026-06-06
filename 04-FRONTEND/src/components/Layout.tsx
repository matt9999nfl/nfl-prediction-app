import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { HealthBanner } from '@/components/HealthBanner'
import { EvaluationBanner } from '@/components/EvaluationBanner'
import { Activity, Database, FlaskConical, Home, Info, Layers } from 'lucide-react'

interface NavItemProps {
  to: string
  label: string
  icon: React.ReactNode
}

function NavItem({ to, label, icon }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        )
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b bg-background">
        <div className="container flex h-14 items-center gap-6">
          <span className="font-bold tracking-tight text-primary">NFL Predictor</span>
          <nav className="flex items-center gap-1 overflow-x-auto">
            <NavItem to="/" label="Dashboard" icon={<Home className="h-4 w-4" />} />
            <NavItem to="/datasets" label="Datasets" icon={<Database className="h-4 w-4" />} />
            <NavItem
              to="/experiments/new"
              label="New Experiment"
              icon={<FlaskConical className="h-4 w-4" />}
            />
            <NavItem to="/experiments" label="Experiments" icon={<Activity className="h-4 w-4" />} />
            <NavItem to="/frameworks" label="Frameworks" icon={<Layers className="h-4 w-4" />} />
            <NavItem to="/about" label="About" icon={<Info className="h-4 w-4" />} />
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 container py-6">
        <HealthBanner />
        <EvaluationBanner />
        <Outlet />
      </main>
    </div>
  )
}
