import React from 'react';
import { Section } from './Section';
import { TypewriterPrompt } from './TypewriterPrompt';

interface TypewriterBeatProps {
  text?: string;
}

export const TypewriterBeat: React.FC<TypewriterBeatProps> = ({
  text = 'Create a high-end online sneaker marketplace',
}) => {
  return (
    <Section enter="slideUp" exit="fadeOut" enterDuration={20} exitDuration={10}>
      <TypewriterPrompt text={text} delay={5} />
    </Section>
  );
};
