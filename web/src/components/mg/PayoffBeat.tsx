import React from 'react';
import { Section } from './Section';
import { GradientText } from './GradientText';
import { FloatingMockup } from './FloatingMockup';

interface PayoffBeatProps {
  text?: string;
  mockupContent?: React.ReactNode;
}

export const PayoffBeat: React.FC<PayoffBeatProps> = ({
  text = 'From prompt to production',
  mockupContent,
}) => {
  return (
    <Section enter="scaleIn" exit="fadeOut" enterDuration={25} exitDuration={15}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
        <GradientText text={text} fontSize={64} fontWeight={800} delay={5} />
        {mockupContent && (
          <FloatingMockup width={600} height={360} perspective={800} delay={20}>
            {mockupContent}
          </FloatingMockup>
        )}
      </div>
    </Section>
  );
};
