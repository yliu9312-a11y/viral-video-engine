import React from 'react';
import { Section } from './Section';
import { FeatureGrid } from './FeatureGrid';

interface GridBeatProps {
  features?: { label: string; icon?: string; description?: string }[];
}

const DEFAULT_FEATURES = [
  { label: 'Auth', icon: '🔐', description: 'User authentication' },
  { label: 'Database', icon: '🗄️', description: 'Data storage' },
  { label: 'Payments', icon: '💳', description: 'Payment processing' },
  { label: 'UI', icon: '🎨', description: 'Beautiful interfaces' },
];

export const GridBeat: React.FC<GridBeatProps> = ({
  features = DEFAULT_FEATURES,
}) => {
  return (
    <Section enter="slideUp" exit="fadeOut" enterDuration={20} exitDuration={10}>
      <FeatureGrid features={features} columns={2} delay={5} />
    </Section>
  );
};
