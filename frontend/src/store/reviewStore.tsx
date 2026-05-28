import { createContext, useContext, useState, ReactNode } from "react";
import type { ReviewRequest } from "@/types/review";

interface ReviewState {
  current: ReviewRequest | null;
  openReview: (req: ReviewRequest) => void;
  closeReview: () => void;
}

const ReviewContext = createContext<ReviewState | null>(null);

export function ReviewProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<ReviewRequest | null>(null);
  return (
    <ReviewContext.Provider value={{
      current,
      openReview: setCurrent,
      closeReview: () => setCurrent(null),
    }}>
      {children}
    </ReviewContext.Provider>
  );
}

export function useReviewStore() {
  const ctx = useContext(ReviewContext);
  if (!ctx) throw new Error("useReviewStore must be inside ReviewProvider");
  return ctx;
}
