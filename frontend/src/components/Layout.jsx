import { Outlet } from 'react-router-dom'

import Sidebar from './Sidebar.jsx'
import Topbar from './Topbar.jsx'
import ToastViewport from './ToastViewport.jsx'

export default function Layout() {
  return (
    <div className="h-screen flex bg-ink-950 text-slate-100">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 overflow-hidden relative">
          <Outlet />
        </main>
      </div>
      <ToastViewport />
    </div>
  )
}
