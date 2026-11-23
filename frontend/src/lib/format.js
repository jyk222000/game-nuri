export const won = (n) => (n == null ? '-' : `${Number(n).toLocaleString('ko-KR')}원`);

const kst = { timeZone: 'Asia/Seoul' };
export const dateKST = (iso) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso).toLocaleDateString('ko-KR', { ...kst, year: 'numeric', month: 'long', day: 'numeric' });
export const dateTimeKST = (iso) =>
  new Date(iso).toLocaleString('ko-KR', { ...kst, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

// 플랫폼은 ERD 코드(PC, PS5 ...)로 오고, 표시 이름은 여기서 바꾼다. (api.md 5번)
export const PLATFORM = {
  PC: 'PC', PS5: 'PS5', PS4: 'PS4', Switch: 'Switch', Switch2: 'Switch 2', XboxSeries: 'Xbox Series', XboxOne: 'Xbox One',
};
export const platformName = (p) => PLATFORM[p] || p;
export const storeName = (s) => STORE_NAME[s] || s;
// ERD에 hue가 없어서 game_id로 표지 색을 만든다. (cover_url이 있으면 그 이미지를 쓴다)
export const hueOf = (id) => (Number(id) * 47) % 360;
export const STORE_NAME = {
  steam: 'Steam', epic: 'Epic Games', gog: 'GOG', humble: 'Humble Store', fanatical: 'Fanatical',
  gmg: 'Green Man Gaming', gamesplanet: 'Gamesplanet', microsoft: 'Microsoft Store', danawa: '다나와',
};
export const EDITION = { digital: '다운로드', physical: '패키지', code: '코드' };
export const CONDITION = { new: '새 상품', used: '중고' };
// edition + item_condition 을 한 줄 라벨로 (예: 패키지 · 중고)
export const editionLabel = (i) => `${EDITION[i.edition] || i.edition}${i.item_condition === 'used' ? ' · 중고' : ''}`;
