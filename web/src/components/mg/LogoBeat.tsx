import React from 'react';
import { Section } from './Section';
import { LogoReveal } from './LogoReveal';
import { GlowTrail } from './GlowTrail';
import { PALETTES } from '../../design-tokens';

interface LogoBeatProps {
  logoText?: string;
  logoIcon?: string;
}

export const LogoBeat: React.FC<LogoBeatProps> = ({
  logoText = 'Layout.dev',
  logoIcon = '✦',
}) => {
  return (
    <Section enter="scaleIn" exit="none" enterDuration={20} exitDuration={0}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24 }}>
        <LogoReveal logoText={logoText} logoIcon={logoIcon} delay={0} />
        <GlowTrail
          pathD="M 200,50 Q 400,10 600,50"
          color={PALETTES.promo.accent}
          trailLength={6}
          dotSize={3}
          delay={15}
        />
      </div>
    </Section>
  );
};
