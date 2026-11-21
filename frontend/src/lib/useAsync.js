import { useEffect, useState, useCallback } from 'react';

// fn() 결과를 { data, error, loading, reload } 로 돌려준다.
export function useAsync(fn, deps = []) {
  const [s, setS] = useState({ data: null, error: null, loading: true });
  const run = useCallback(() => {
    let alive = true;
    setS((p) => ({ ...p, loading: true, error: null }));
    fn().then(
      (data) => alive && setS({ data, error: null, loading: false }),
      (error) => alive && setS({ data: null, error, loading: false }),
    );
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => run(), [run]);
  return { ...s, reload: run };
}
