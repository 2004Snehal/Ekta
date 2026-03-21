"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { driver, Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./tutorial.css"; // Custom dark theme overrides
import { getTutorialSteps } from "./steps";
import { usePathname } from "next/navigation";

interface TutorialContextType {
  startTutorial: () => void;
  resetTutorial: () => void;
}

const TutorialContext = createContext<TutorialContextType | null>(null);

export function TutorialProvider({ children }: { children: React.ReactNode }) {
  const [driverObj, setDriverObj] = useState<Driver | null>(null);
  const pathname = usePathname();
  const mounted = useRef(false);

  useEffect(() => {
    // Determine steps based on current path
    const steps = getTutorialSteps(pathname);

    // Initialize driver.js
    const instance = driver({
      showProgress: true,
      animate: true,
      opacity: 0.6,
      steps: steps,
      popoverClass: 'driverjs-theme',
      allowClose: true,
      stagePadding: 6,
      popoverOffset: 14,       // consistent gap between highlight box and popover arrow
      smoothScroll: false,     // sidebar links are position:fixed — scrolling shifts coords
      doneBtnText: 'Finish',
      nextBtnText: 'Next',
      prevBtnText: 'Back',
      onDestroyStarted: () => {
        // Automatically mark as seen when skipped or finished, without manual confirmation
        instance.destroy();
        localStorage.setItem("frammer_tutorial_seen", "true");
      },
    });

    setDriverObj(instance);
    
    return () => instance.destroy();
  }, [pathname]);

  // Auto-start for first-time users
  useEffect(() => {
    if (!driverObj || mounted.current) return;

    // Only auto-start on the main dashboard to be less intrusive
    const isDashboard = pathname === "/" || pathname === "/dashboard";
    const hasSeen = localStorage.getItem("frammer_tutorial_seen");

    if (isDashboard && !hasSeen) {
      mounted.current = true;
      // Small delay to ensure UI is ready
      setTimeout(() => {
        driverObj.drive();
      }, 1500);
    }
  }, [driverObj, pathname]);

  const startTutorial = () => {
    driverObj?.drive();
  };

  const resetTutorial = () => {
    localStorage.removeItem("frammer_tutorial_seen");
    startTutorial();
  };

  return (
    <TutorialContext.Provider value={{ startTutorial, resetTutorial }}>
      {children}
    </TutorialContext.Provider>
  );
}

export function useTutorial() {
  const context = useContext(TutorialContext);
  if (!context) {
    throw new Error("useTutorial must be used within a TutorialProvider");
  }
  return context;
}
