import React from 'react';
import { Section } from './Section';
import { GradientText } from './GradientText';
import { MarqueeText } from './MarqueeText';

interface ClosingBeatProps {
  text?: string;
  marqueeText?: string;
}

export const ClosingBeat: React.FC<ClosingBeatProps> = ({
  text = 'Stop prompting, start shipping',
  marqueeText = 'Ship fast • Build smart • Launch today',
}) => {
  return (
    <Section enter="fadeIn" exit="fadeOut" enterDuration={20} exitDuration={15}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32 }}>
        <GradientText text={text} fontSize={56} fontWeight={800} delay={5} />
        <MarqueeText text={marqueeText} speed={2} />
      </div>
    </Section>
  );
};
