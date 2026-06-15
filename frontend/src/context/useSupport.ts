import { useContext } from "react";
import { SupportContext } from "@/context/support-context-value";

export const useSupport = () => {
  const context = useContext(SupportContext);
  if (!context) {
    throw new Error("useSupport must be inside SupportProvider");
  }
  return context;
};
