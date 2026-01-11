'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import {
  LayoutDashboard,
  Server,
  Boxes,
  HardDrive,
  Activity,
  FlaskConical,
  Settings,
  BookOpen,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Nodes', href: '/nodes', icon: Server },
  { name: 'Deployments', href: '/deployments', icon: Boxes },
  { name: 'Hardware', href: '/hardware', icon: HardDrive },
  { name: 'Monitoring', href: '/monitoring', icon: Activity },
  { name: 'MLFlow', href: '/mlflow', icon: FlaskConical },
]

const secondaryNavigation = [
  { name: 'Documentation', href: '/docs', icon: BookOpen },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-64 bg-surface-900/50 border-r border-surface-800 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-surface-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-500/20 flex items-center justify-center">
            <Server className="w-5 h-5 text-primary-400" />
          </div>
          <div>
            <h1 className="font-bold text-surface-100">RPi K8s</h1>
            <p className="text-xs text-surface-500">Control Panel</p>
          </div>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary-500/10 text-primary-400 border border-primary-500/20'
                  : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800'
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      {/* Secondary Navigation */}
      <div className="px-3 py-4 border-t border-surface-800 space-y-1">
        {secondaryNavigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-surface-800 text-surface-100'
                  : 'text-surface-500 hover:text-surface-300 hover:bg-surface-800/50'
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </Link>
          )
        })}
      </div>

      {/* Cluster Status */}
      <div className="px-4 py-4 border-t border-surface-800">
        <div className="flex items-center gap-2 text-xs text-surface-500">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
          </span>
          Cluster Online
        </div>
      </div>
    </aside>
  )
}
