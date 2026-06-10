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
      {/* Nav bar — hidden on editor page for more space */}
      {page !== 'editor' && (
        <nav style={styles.nav}>
          <div style={styles.navInner}>
            <span style={styles.logo}>VST</span>
          </div>
        </nav>
      )}

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
    height: 52,
  },
  logo: {
    fontFamily: 'var(--font-mono)',
    fontWeight: 700,
    fontSize: 18,
    color: 'var(--accent)',
    letterSpacing: '0.05em',
  },
};

export default App;
