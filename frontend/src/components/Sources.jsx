import React, { useEffect, useState } from 'react';
import { fetchShows } from '../api';
import { Link } from 'react-router-dom';

export default function Sources() {
  const [shows, setShows] = useState([]);
  useEffect(() => {
    fetchShows().then(setShows).catch(console.error);
  }, []);

  return (
    <div className="sources-list">
      <button className="new-source">+ New Source</button>
      <table>
        <thead>
          <tr><th>Name</th><th>Downloaded</th><th>Size</th><th>Action</th></tr>
        </thead>
        <tbody>
          {shows.map(s => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{/* fetched via individual show? */}</td>
              <td>{(s.size/1e9).toFixed(2)} GB</td>
              <td><Link to={`/shows/${encodeURIComponent(s.name)}`}>Edit</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}