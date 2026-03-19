'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';

export const PROFILE_KEYS = [
  'founder',
  'client_success',
  'operations',
  'editorial',
  'tech_product',
] as const;

export type ProfileKey = (typeof PROFILE_KEYS)[number];

export type ProfileDefinition = {
  key: ProfileKey;
  displayName: string;
  focus: string;
  icon: string;
  description: string;
  defaultView: string;
};

export const PROFILES: Record<ProfileKey, ProfileDefinition> = {
  founder: {
    key: 'founder',
    displayName: 'Founders / Leadership',
    focus: 'Strategic growth, revenue impact, portfolio',
    icon: 'C-suite',
    description: 'High-level strategic view of the entire operation',
    defaultView: '/dashboard',
  },
  client_success: {
    key: 'client_success',
    displayName: 'Client Success',
    focus: 'Client health, adoption, retention signals',
    icon: 'CS',
    description: 'Client-centric health monitoring and adoption tracking',
    defaultView: '/dashboard/analysis',
  },
  operations: {
    key: 'operations',
    displayName: 'Operations',
    focus: 'Throughput, bottlenecks, team efficiency',
    icon: 'Ops',
    description: 'Operational throughput and process efficiency',
    defaultView: '/dashboard/usage',
  },
  editorial: {
    key: 'editorial',
    displayName: 'Editorial / Production',
    focus: 'Content quality, type mix, editorial decisions',
    icon: 'Edit',
    description: 'Content pipeline and editorial decision support',
    defaultView: '/dashboard/funnel',
  },
  tech_product: {
    key: 'tech_product',
    displayName: 'Tech / Product',
    focus: 'Data quality, platform health, system metrics',
    icon: 'Tech',
    description: 'Technical health monitoring and data quality',
    defaultView: '/dashboard/explorer',
  },
};

type ProfileContextValue = {
  profile: ProfileKey;
  profileDef: ProfileDefinition;
  setProfile: (key: ProfileKey) => void;
};

const STORAGE_KEY = 'frammer.profile';
const DEFAULT_PROFILE: ProfileKey = 'operations';

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfileState] = useState<ProfileKey>(DEFAULT_PROFILE);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    if ((PROFILE_KEYS as readonly string[]).includes(saved)) {
      setProfileState(saved as ProfileKey);
    }
  }, []);

  const setProfile = (key: ProfileKey) => {
    setProfileState(key);
    window.localStorage.setItem(STORAGE_KEY, key);
  };

  const value = useMemo<ProfileContextValue>(() => {
    return {
      profile,
      profileDef: PROFILES[profile],
      setProfile,
    };
  }, [profile]);

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) {
    throw new Error('useProfile must be used within ProfileProvider');
  }
  return ctx;
}