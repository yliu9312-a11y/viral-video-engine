import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';

export const VstVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: 'black',
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          color: 'white',
          fontSize: 48,
          fontFamily: 'sans-serif',
          opacity: Math.min(1, frame / (fps * 0.5)),
        }}
      >
        VST - ViralStructTransfer
      </div>
    </AbsoluteFill>
  );
};
