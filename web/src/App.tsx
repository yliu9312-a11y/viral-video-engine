import { useState, useEffect } from 'react';
import HomePage from './pages/HomePage';
import EditorPage from './pages/EditorPage';
import { usePipelineStore } from './stores/pipeline';

type Page = 'pipeline' | 'editor';

function App() {
  const [page, setPage] = useState<Page>('pipeline');
  const store = usePipelineStore();

  // Auto-navigate to editor when pipeline completes
  useEffect(() => {
    if (store.stage === 'done') {
      setPage('editor');
    }
  }, [store.stage]);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-root)' }}>
      <nav style={styles.nav}>
        <div style={styles.navInner}>
          <span style={styles.logo}>VST</span>
          <div style={styles.tabs}>
            <button
              style={{ ...styles.tabBtn, ...(page === 'pipeline' ? styles.tabActive : {}) }}
              onClick={() => setPage('pipeline')}
            >
              流水线
            </button>
            <button
              style={{ ...styles.tabBtn, ...(page === 'editor' ? styles.tabActive : {}) }}
              onClick={() => setPage('editor')}
            >
              🎬 编辑器
            </button>
          </div>
        </div>
      </nav>

      <div style={{ animation: 'fadeInUp 0.3s ease-out' }}>
        {page === 'pipeline' && <HomePage />}
        {page === 'editor' && <EditorPage onBack={() => setPage('pipeline')} />}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  nav: {
    background: 'rgba(6, 6, 10, 0.85)',
    backdropFilter: 'blur(12px)',
    borderBottom: '1px solid var(--border)',
    position: 'sticky' as const,
    top: 0,
    zIndex: 100,
  },
  navInner: {
    maxWidth: 1200,
    margin: '0 auto',
    padding: '0 1.5rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 52,
  },
  logo: {
    fontFamily: 'var(--font-mono)',
    fontWeight: 700,
    fontSize: 18,
    color: 'var(--accent)',
    letterSpacing: '0.05em',
  },
  tabs: {
    display: 'flex',
    gap: 0,
  },
  tabBtn: {
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: 'var(--text-muted)',
    fontSize: 14,
    fontWeight: 600,
    fontFamily: 'var(--font-display)',
    padding: '14px 20px',
    cursor: 'pointer',
    transition: 'color 0.2s, border-color 0.2s',
  },
  tabActive: {
    color: 'var(--text-primary)',
    borderBottomColor: 'var(--accent)',
  },
};

export default App;
