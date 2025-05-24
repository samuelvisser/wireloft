import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchShow, updateShow } from '../api';

export default function ShowEditor() {
  const { name } = useParams();
  const [config, setConfig] = useState(null);
  useEffect(() => {
    fetchShow(name).then(data => setConfig(data.config)).catch(console.error);
  }, [name]);

  function handleSave() {
    updateShow(name, config).then(() => alert('Saved')).catch(console.error);
  }

  if (!config) return <div>Loading...</div>;
  return (
    <div className="editor">
      <h2>Editing: {name}</h2>
      <label>Source URL</label>
      <input value={config.url} onChange={e => setConfig({ ...config, url: e.target.value })} />
      {/* more fields: media profile, frequency toggles, etc. */}
      <button onClick={handleSave}>Save Settings</button>
    </div>
  );
}