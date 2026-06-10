import { Composition } from 'remotion';
import { VstVideo } from './composition/VstVideo';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="VstVideo"
      component={VstVideo}
      durationInFrames={300}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
