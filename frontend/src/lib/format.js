export const won = (n) => (n == null ? '-' : `${Number(n).toLocaleString('ko-KR')}원`);

const kst = { timeZone: 'Asia/Seoul' };
export const dateKST = (iso) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso).toLocaleDateString('ko-KR', { ...kst, year: 'numeric', month: 'long', day: 'numeric' });
export const dateTimeKST = (iso) =>
  new Date(iso).toLocaleString('ko-KR', { ...kst, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

export const PLATFORM = { pc: 'PC', ps: 'PS', xbox: 'Xbox', switch: 'Switch' };
export const STORE_NAME = {
  steam: 'Steam', epic: 'Epic Games', gog: 'GOG', humble: 'Humble Store', fanatical: 'Fanatical',
  gmg: 'Green Man Gaming', gamesplanet: 'Gamesplanet', microsoft: 'Microsoft Store', danawa: '다나와',
};
export const EDITION = { digital: '다운로드', physical: '패키지', used: '중고 패키지' };
