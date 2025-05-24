import React, { useEffect, useState } from 'react';
import { fetchOverview } from '../api';

export default function Overview() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchOverview().then(setData).catch(console.error);
  }, []);

  if (!data) return <div>Loading...</div>;
  return (
    <div className="overview">
      <div className="card">Shows: {data.shows}</div>
      <div className="card">Sources: {/* TODO: fetch sources count */}</div>
      <div className="card">Downloads: {data.files}</div>
      <div className="card">Library Size: { (data.library_size/1e9).toFixed(2) } GB</div>
    </div>
  );
}