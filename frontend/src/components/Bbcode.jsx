import { Fragment } from 'react';

// Steam 리뷰의 BBCode([b], [h1], [list], [*] ...)를 React 요소로 바꾼다.
// HTML 문자열을 만들지 않으므로 XSS 위험이 없다. 모르는 태그는 지우고 안의 글만 남긴다.
// 리뷰가 중간에 잘려 닫는 태그가 없어도 깨지지 않게 끝에서 자동으로 닫는다.

const TAG_RE = /\[(\/?)([a-z0-9*]+)(?:=([^\]]*))?\]/gi;
const INLINE = { b: 'strong', i: 'em', u: 'u', s: 's', strike: 's' };
const HEADING = new Set(['h1', 'h2', 'h3']);
const LIST = new Set(['list', 'olist']);
const SKIP = new Set(['img', 'previewyoutube']); // 이미지·영상 코드는 글이 아니라 표시하지 않는다

function parse(text) {
  const root = { tag: 'root', children: [] };
  const stack = [root];
  const top = () => stack[stack.length - 1];
  const close = (name) => {
    const idx = stack.map((n) => n.tag).lastIndexOf(name);
    if (idx > 0) stack.length = idx;
  };

  let last = 0;
  let m;
  TAG_RE.lastIndex = 0;
  while ((m = TAG_RE.exec(text))) {
    if (m.index > last) top().children.push(text.slice(last, m.index));
    last = TAG_RE.lastIndex;
    const closing = m[1] === '/';
    const name = m[2].toLowerCase();

    if (closing) {
      if (LIST.has(name)) close('li');
      close(name);
    } else if (name === 'hr') {
      top().children.push({ tag: 'hr', children: [] });
    } else if (name === '*') {
      close('li');
      const node = { tag: 'li', children: [] };
      top().children.push(node);
      stack.push(node);
    } else {
      const node = { tag: name, arg: m[3], children: [] };
      top().children.push(node);
      stack.push(node);
    }
  }
  if (last < text.length) top().children.push(text.slice(last));
  return root.children;
}

function render(nodes, key = '') {
  return nodes.map((n, i) => {
    const k = `${key}.${i}`;
    if (typeof n === 'string') return <Fragment key={k}>{n}</Fragment>;
    const kids = render(n.children, k);
    if (n.tag === 'hr') return <hr key={k} />;
    if (SKIP.has(n.tag)) return null;
    if (INLINE[n.tag]) {
      const T = INLINE[n.tag];
      return <T key={k}>{kids}</T>;
    }
    if (HEADING.has(n.tag)) return <div key={k} className={`bb-h bb-${n.tag}`}>{kids}</div>;
    if (n.tag === 'list') return <ul key={k} className="bb-list">{kids}</ul>;
    if (n.tag === 'olist') return <ol key={k} className="bb-list">{kids}</ol>;
    if (n.tag === 'li') return <li key={k}>{kids}</li>;
    if (n.tag === 'quote') return <blockquote key={k} className="bb-quote">{kids}</blockquote>;
    if (n.tag === 'code' || n.tag === 'noparse') return <code key={k}>{kids}</code>;
    if (n.tag === 'spoiler') return <span key={k} className="bb-spoiler">{kids}</span>;
    if (n.tag === 'url') {
      const href = n.arg || (typeof n.children[0] === 'string' ? n.children[0] : '');
      if (/^https?:\/\//i.test(href)) {
        return <a key={k} href={href} target="_blank" rel="noopener noreferrer nofollow">{kids}</a>;
      }
    }
    return <Fragment key={k}>{kids}</Fragment>; // 모르는 태그: 글만 남김
  });
}

export default function Bbcode({ text }) {
  return <div className="bb">{render(parse(String(text ?? '')))}</div>;
}
