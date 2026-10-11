import { useEffect, useState } from 'react'

const dateOptions: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
  year: 'numeric',
}

function formatLocalDate(): string {
  return new Intl.DateTimeFormat(undefined, dateOptions).format(new Date())
}

export function useCurrentLocalDate(): string {
  const [date, setDate] = useState(formatLocalDate)

  useEffect(() => {
    let timer: number

    function updateAtNextLocalMidnight() {
      setDate(formatLocalDate())
      const now = new Date()
      const nextMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
      timer = window.setTimeout(updateAtNextLocalMidnight, nextMidnight.getTime() - now.getTime() + 50)
    }

    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') {
        window.clearTimeout(timer)
        updateAtNextLocalMidnight()
      }
    }

    updateAtNextLocalMidnight()
    document.addEventListener('visibilitychange', refreshWhenVisible)

    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [])

  return date
}
