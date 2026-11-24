import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {Episode, Short} from './studio/Episode';
// engine/export_remotion.py writes src/data/<EpN>_full.json; engine/export_shorts.py writes src/data/<EpN>_short_<key>.json
import full from './data/EpN_full.json';
import shortA from './data/EpN_short_A.json';
const withShots = (x) => ({...full, ...x});

const Root = () => (
  <>
    <Composition id="EpisodeFull" component={Episode} defaultProps={{data: full}}
      durationInFrames={Math.ceil(full.duration * full.fps)} fps={full.fps} width={1920} height={1080} />
    <Composition id="ShortA" component={Short} defaultProps={{data: withShots(shortA)}}
      durationInFrames={Math.ceil(shortA.duration * 30)} fps={30} width={1080} height={1920} />
  </>
);
registerRoot(Root);
