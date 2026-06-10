import React from 'react';
import { Section } from './Section';
import { HeroTitle } from './HeroTitle';
import { GlowTrail } from './GlowTrail';

interface HookBeatProps {
  text?: string;
}

export const HookBeat: React.FC<HookBeatProps> = ({
  text = 'What if one prompt could build your side hustle',
}) => {
  return (
    <Section enter="fadeIn" exit="fadeOut" enterDuration={25} exitDuration={15}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
        <HeroTitle text={text} variant="hero" gradient enterDelay={10} />
        <GlowTrail
          pathD="M 100,30 Q 300,0 500,30 Q 700,60 900,30"
          color="#3B82F6"
          trailLength={8}
          dotSize={4}
          delay={30}
        />
      </div>
    </Section>
  );
};
