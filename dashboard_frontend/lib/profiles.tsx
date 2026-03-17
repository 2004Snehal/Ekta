'use client';

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

export type ProfileKey = 'founder' | 'client_success' | 'operations' | 'editorial' | 'tech_product';

export interface ProfileDef {
  key: ProfileKey;
  displayName: string;
  focus: string;
  defaultKpis: string[];
  defaultView: string;
  description: string;
  icon: string; // single char/emoji for compact display
}

export const PROFILES: Record<ProfileKey, ProfileDef> = {
  founder: {
    key: 'founder',
    displayName: 'Founders / Leadership',
    focus: 'Strategic growth, revenue impact, portfolio',
    defaultKpis: ['publish_rate', 'total_duration', 'growth_pct'],
    defaultView: '/dashboard',
    description: 'High-level strategic view of the entire operation',
    icon: 'F',
  },
  client_success: {
    key: 'client_success',
    displayName: 'Client Success',
    focus: 'Client health, adoption, retention signals',
    defaultKpis: ['active_channels', 'publish_rate', 'usage_trend'],
    defaultView: '/dashboard/analysis',
    description: 'Client-centric health monitoring and adoption tracking',
    icon: 'C',
  },
  operations: {
    key: 'operations',
    displayName: 'Operations',
    focus: 'Throughput, bottlenecks, team efficiency',
    defaultKpis: ['processed_videos', 'publish_rate', 'avg_turnaround'],
    defaultView: '/dashboard/usage',
    description: 'Operational throughput and process efficiency',
    icon: 'O',
  },
  editorial: {
    key: 'editorial',
    displayName: 'Editorial / Production',
    focus: 'Content quality, type mix, editorial decisions',
    defaultKpis: ['output_type_mix', 'input_type_trend', 'publish_rate'],
    defaultView: '/dashboard/funnel',
    description: 'Content pipeline and editorial decision support',
    icon: 'E',
  },
  tech_product: {
    key: 'tech_product',
    displayName: 'Tech / Product',
    focus: 'Data quality, platform health, system metrics',
    defaultKpis: ['missing_data_pct', 'error_rate', 'platform_coverage'],
    defaultView: '/dashboard/explorer',
    description: 'Technical health monitoring and data quality',
    icon: 'T',
  },
};

export const PROFILE_KEYS = Object.keys(PROFILES) as ProfileKey[];

interface ProfileContextValue {
  profile: ProfileKey;
  profileDef: ProfileDef;
  setProfile: (key: ProfileKey) => void;
}

const ProfileContext = createContext<ProfileContextValue>({
  profile: 'operations',
  profileDef: PROFILES.operations,
  setProfile: () => {},
});

const STORAGE_KEY = 'frammer:profile';

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState<ProfileKey>('operations');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ProfileKey | null;
    if (stored && stored in PROFILES) setProfileState(stored);
  }, []);

  const setProfile = (key: ProfileKey) => {
    setProfileState(key);
    localStorage.setItem(STORAGE_KEY, key);
  };

  return (
    <ProfileContext.Provider value={{ profile, profileDef: PROFILES[profile], setProfile }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  return useContext(ProfileContext);
}
