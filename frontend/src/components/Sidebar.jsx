import React from 'react';
import { NavLink } from 'react-router-dom';

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <h1 className="logo">Wireloft</h1>
      <nav>
        <NavLink to="/overview" className={({ isActive }) => isActive ? 'active' : ''}>Overview</NavLink>
        <NavLink to="/sources" className={({ isActive }) => isActive ? 'active' : ''}>Sources</NavLink>
      </nav>
    </aside>
  );
}