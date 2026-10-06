import {createContext, useContext, useEffect, useState} from 'react';

import {Brain, type Snapshot} from './brain';
import {light, type Palette} from './theme';

export const BrainContext = createContext<Brain | null>(null);
export const ThemeContext = createContext<Palette>(light);

export function useBrain(): Brain {
  const brain = useContext(BrainContext);
  if (!brain) {
    throw new Error('Brain is missing');
  }
  return brain;
}

export function useTheme(): Palette {
  return useContext(ThemeContext);
}

export function useSnapshot(brain: Brain): Snapshot {
  const [snapshot, setSnapshot] = useState(brain.snapshot);
  useEffect(() => brain.subscribe(setSnapshot), [brain]);
  return snapshot;
}
