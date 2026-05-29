import { useEffect, useState } from "react";

// 奔跑小人帧动画 —— 腿脚交替 + 手臂摆动
const FRAMES = [
  " ᕕ( ᐛ )ᕗ",
  " ᕕ(ᐛ  )ᕗ",
  " ᕕ( ᐛ )ᕗ",
  " ᕕ(  ᐛ)ᕗ",
];

const TRAIL = ["·", "··", "···", "··", "·", ""];

export default function RunnerLoader() {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % FRAMES.length);
    }, 180);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-center gap-1 text-[13px] font-mono select-none">
      <span className="text-[#aaa] dark:text-[#555] transition-none whitespace-pre">
        {FRAMES[frame]}
      </span>
      <span className="text-[#ccc] dark:text-[#444] text-[10px] w-4">
        {TRAIL[frame % TRAIL.length]}
      </span>
    </div>
  );
}
