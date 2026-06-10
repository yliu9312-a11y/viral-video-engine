import React from 'react';
import { Section } from './Section';
import { GlassCard } from './GlassCard';
import { MarqueeText } from './MarqueeText';
import { STAGGER } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, FONTS } from '../../design-tokens';

interface FeatureItem {
  icon: string;
  title: string;
  desc: string;
}

interface FeaturesBeatProps {
  features?: FeatureItem[];
  marqueeText?: string;
}

const DEFAULT_FEATURES: FeatureItem[] = [
  { icon: '🛍️', title: 'Product Pages', desc: 'Beautiful product displays' },
  { icon: '💳', title: 'Checkout', desc: 'Seamless payment flow' },
  { icon: '📊', title: 'Analytics', desc: 'Real-time insights' },
  { icon: '🎨', title: 'Themes', desc: 'Customizable design' },
];

export const FeaturesBeat: React.FC<FeaturesBeatProps> = ({
  features = DEFAULT_FEATURES,
  marqueeText = 'Build • Launch • Scale • Grow • Ship • Iterate',
}) => {
  return (
    <Section enter="fadeIn" exit="fadeOut" enterDuration={20} exitDuration={15}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32, width: '100%' }}>
        {/* Feature cards */}
        <div style={{ display: 'flex', gap: 20, justifyContent: 'center', flexWrap: 'wrap' }}>
          {features.map((f, i) => (
            <GlassCard key={i} width={200} height={160} delay={STAGGER.card * i} float>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>{f.icon}</div>
                <div style={{ fontSize: FONT_SIZES.body, fontWeight: FONT_WEIGHTS.bold, color: PALETTES.promo.secondary, fontFamily: FONTS.primary }}>
                  {f.title}
                </div>
                <div style={{ fontSize: FONT_SIZES.caption, color: PALETTES.promo.textMuted, fontFamily: FONTS.primary, marginTop: 4 }}>
                  {f.desc}
                </div>
              </div>
            </GlassCard>
          ))}
        </div>

        {/* Marquee */}
        <MarqueeText text={marqueeText} speed={1} />
      </div>
    </Section>
  );
};
