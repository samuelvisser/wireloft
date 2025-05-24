import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Overview from './components/Overview';
import Sources from './components/Sources';
import ShowEditor from './components/ShowEditor';

export default function App() {
  return (
    <div className="app">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/overview" element={<Overview />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/shows/:name" element={<ShowEditor />} />
          <Route path="*" element={<Navigate replace to="/overview" />} />
        </Routes>
      </main>
    </div>
  );
}