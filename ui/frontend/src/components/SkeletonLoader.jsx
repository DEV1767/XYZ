import React from 'react'

export function SkeletonLoader({ type = 'table' }) {
  if (type === 'metric') {
    return (
      <div className="p-3 bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] animate-pulse">
        <div className="h-3 w-20 bg-[#EFECE2] dark:bg-[#1E2633] rounded mb-2"></div>
        <div className="h-6 w-32 bg-[#D5D0C3] dark:bg-[#2A3444] rounded mb-1"></div>
        <div className="h-2.5 w-16 bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
      </div>
    )
  }

  if (type === 'chart') {
    return (
      <div className="h-64 bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] p-4 flex flex-col justify-between animate-pulse">
        <div className="flex justify-between">
          <div className="h-4 w-32 bg-[#D5D0C3] dark:bg-[#2A3444] rounded"></div>
          <div className="h-4 w-20 bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
        </div>
        <div className="h-40 bg-[#EFECE2]/50 dark:bg-[#0B0E14] rounded my-auto flex items-end gap-2 p-2">
          {[40, 65, 55, 80, 70, 95, 60, 85, 90, 75].map((h, i) => (
            <div key={i} className="flex-1 bg-[#D5D0C3] dark:bg-[#2A3444] rounded-t" style={{ height: `${h}%` }}></div>
          ))}
        </div>
        <div className="h-3 w-48 bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
      </div>
    )
  }

  return (
    <div className="space-y-2 p-3 bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] animate-pulse">
      <div className="h-4 w-1/3 bg-[#D5D0C3] dark:bg-[#2A3444] rounded"></div>
      <div className="space-y-1.5 pt-2">
        <div className="h-3 w-full bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
        <div className="h-3 w-5/6 bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
        <div className="h-3 w-4/6 bg-[#EFECE2] dark:bg-[#1E2633] rounded"></div>
      </div>
    </div>
  )
}
