import React, { useEffect, useRef, useState } from "react";
import "./App.css";
import logo from "./assets/hallym-logo.jpeg";
import {
  analyzeTrack,
  fetchDeptList,
  fetchDeptTracks,
} from "./api";
import type {
  AnalyzeResponse,
  AnalyzeCourseInput,
  DeptTracksResponse,
  CollegeGroup,
  TrackDetailInfo,
  TrackResultInfo,
  RuleResultInfo
} from "./api";

function ChecklistIcon() {
  return (
    <svg viewBox="0 0 24 24" className="method-svg" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M8 9.5l1.6 1.6L13 7.7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 9h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M8 15h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function TrackExploreIcon() {
  return (
    <svg viewBox="0 0 24 24" className="method-svg" aria-hidden="true">
      <path d="M4 5.8c2.4-1 5-1 7.4.1v12.8c-2.4-1.1-5-1.1-7.4-.1z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M12.6 5.9c2.4-1.1 5-1.1 7.4-.1v12.8c-2.4-1-5-1-7.4.1z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M8 9h1.2M8 12h1.2M15 9h2M15 12h2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function TargetStatusIcon() {
  return (
    <svg viewBox="0 0 40 40" className="target-status-svg" aria-hidden="true">
      <circle cx="20" cy="21" r="13" fill="#f04783" />
      <circle cx="20" cy="21" r="8.4" fill="#ffd6e4" />
      <circle cx="20" cy="21" r="4.3" fill="#f04783" />
      <path d="M22 18.5 30.5 10" stroke="#42b8dc" strokeWidth="3.4" strokeLinecap="round" />
      <path d="M28.7 11.8h5.4l-3.2 3.2h-5.4z" fill="#5ed0ee" />
      <path d="M27.2 13.3v-5.4L24 11.1v5.4z" fill="#2f9fcc" />
      <circle cx="20" cy="21" r="2" fill="#ffffff" />
    </svg>
  );
}

type Course = {
  id: number;
  name: string;
  credit: string;
  grade: string;
};

type DeptAnalysisBundle = {
  deptName: string;
  tracksData: DeptTracksResponse;
  analyzeResult: AnalyzeResponse;
};

type CombinedTrackInfo = TrackDetailInfo & {
  dept_name: string;
  unique_id: string;
};

type CombinedTrackResultInfo = TrackResultInfo & {
  dept_name: string;
  unique_id: string;
};

type TrackSummaryModule = DeptTracksResponse["modules"][number];

const creditOptions = ["1", "2", "3", "4", "5", "6"];
const gradeOptions = ["이수","미이수(F)","Pass", "Non-pass"];
const MAX_SELECTED_MAJORS = 4;

const majorColorPalette = [
  { bg: "#E8F1FF", text: "#3566C8", border: "#B8CEF6" },
  { bg: "#EAF6F8", text: "#327C8D", border: "#BBDDE4" },
  { bg: "#F3EEFF", text: "#7A5AC8", border: "#D7CBF5" },
  { bg: "#EEF7F0", text: "#4F8A63", border: "#C8E3CF" },
  { bg: "#EAF4FF", text: "#3F78AD", border: "#BED8F0" },
  { bg: "#F2F0FB", text: "#6B63A8", border: "#D2CEEE" },
];

const getMajorColorStyle = (index: number): React.CSSProperties => {
  const color = majorColorPalette[Math.max(index, 0) % majorColorPalette.length];
  return {
    "--major-bg": color.bg,
    "--major-text": color.text,
    "--major-border": color.border,
  } as React.CSSProperties;
};


const emojiList = ["📚", "🔬", "🎨", "🏛️", "⚗️", "📐", "💡", "🌱", "🔭", "📊", "🧪", "🎓", "🌿", "📝", "🔍"];
const getEmoji = (name: string) => {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return emojiList[Math.abs(hash) % emojiList.length];
};

const condenseRuleSummary = (text: string): string => {
  const parts = text.split(/\s+및\s+/);
  const creditPattern = /^(.+)에서\s+(\d+(?:학점|과목)\s+이상\s+이수)$/;
  // 에서가 붙어 있을 수도 있으므로 non-greedy + 선택적 에서로 캡처
  const allPattern = /^(.+?)(?:에서)?\s+모든\s+과목\s+이수$/;
  const condensed: string[] = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i].trim();
    const creditMatch = part.match(creditPattern);
    const allMatch = part.match(allPattern);
    if (creditMatch) {
      const suffix = creditMatch[2].replace(/\s+/g, " ").trim();
      const modules = [creditMatch[1].trim()];
      let j = i + 1;
      while (j < parts.length) {
        const nm = parts[j].trim().match(creditPattern);
        if (nm && nm[2].replace(/\s+/g, " ").trim() === suffix) {
          modules.push(nm[1].trim());
          j++;
        } else break;
      }
      condensed.push(modules.length >= 2 ? `${modules.join(", ")}에서 각 ${suffix}` : part);
      i = j;
    } else if (allMatch) {
      const modules = [allMatch[1].trim()];
      let j = i + 1;
      while (j < parts.length) {
        const nm = parts[j].trim().match(allPattern);
        if (nm) { modules.push(nm[1].trim()); j++; } else break;
      }
      // 단일 모듈: "X에서 모든 과목 이수" / 복수 모듈: "X, Y, Z 모든 과목 이수"
      condensed.push(modules.length >= 2
        ? `${modules.join(", ")} 모든 과목 이수`
        : `${modules[0]}에서 모든 과목 이수`);
      i = j;
    } else {
      condensed.push(part);
      i++;
    }
  }
  return condensed.join(" 및 ");
};

const buildModuleFallbackSummary = (modules: TrackSummaryModule[], moduleNameText: string) => {
  if (modules.length === 0) return moduleNameText ? `${moduleNameText} 관련 과목 이수` : "트랙 관련 과목 이수";

  const counts = modules.map(module => module.courses.length).filter(count => count > 0);
  const allSameCount = counts.length === modules.length && counts.every(count => count === counts[0]);
  if (allSameCount && counts[0]) {
    return `${moduleNameText}에서 각 ${counts[0]}과목 이수`;
  }

  return modules
    .map(module => `${module.module_name}에서 ${module.courses.length || 1}과목 이수`)
    .join(" 및 ");
};

const formatDeptName = (deptName: string) =>
  deptName.replace("언론방송융합미디어전공 / 디지털미디어콘텐츠전공", "언론방송융합미디어전공\n디지털미디어콘텐츠전공");

const formatTrackName = (trackName: string) => {
  const trimmed = trackName.trim();
  return trimmed.replace(/^(.*?)\s*트랙$/, (_, prefix) => prefix.replace(/\s+/g, "") + " 트랙");
};

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const normalizeRuleSummaryText = (text: string, moduleNames: string[] = []) => {
  let normalized = text
    .replace(/듣기/g, "이수")
    .replace(/수강/g, "이수")
    .replace(/교과목/g, "과목")
    .replace(/관련\s*필수\s*과목/g, "필수 과목")
    .replace(/관련필수과목/g, "필수 과목")
    .replace(/관련필수/g, "필수 과목")
    .replace(/필수\s*과목\s*범주\s*\((?:[^()]*|\([^()]*\))*\)/g, "필수 과목 범주")
    .replace(/필수\s*과목\s*범주\s*\)/g, "필수 과목 범주")
    .replace(/필수\s*과목\s*범주\s+확인/g, "필수 과목 범주 이수")
    .replace(/필수\s*과목\s*\((?:[^()]*|\([^()]*\))*\)/g, "필수 과목")
    .replace(/필수\s*과목\s*\)/g, "필수 과목")
    .replace(/필수\s*과목\s+이수\s+및\s+필수\s*과목\s+외\s+추가/g, "필수 과목 이수 및 추가")
    .replace(/트랙\s*전체\s*\d+과목\s*이상\s*이수\s*및\s*(?=트랙\s*전체\s*\d+학점)/g, "")
    .replace(/(?<![,가-힣])에서\s*(모든\s*과목\s*이수)/g, " $1")
    .replace(/\S+\s+\d+(?:,\s*\d+)*번\s*과목(?:\([^)]+\))?\s*이수/g, "필수 과목 이수")
    .replace(/(?:필수\s*과목\s*이수\s*및\s*)+필수\s*과목\s*이수/g, "필수 과목 이수")
    .replace(/택\s*(\d+)\s*이수/g, "$1과목 이상 이수")
    .replace(/(\d+)\s*개\s*이상\s*이수/g, "$1과목 이상 이수")
    .replace(/(\d+)\s*,\s*(\d+)\s*이수/g, "$1, $2 중 1과목 이상 이수")
    .replace(/(\d+)\s*학점\s*이상\s*이수/g, "$1학점 이상 이수")
    .replace(/(\d+)\s*학점\s*이상(?!\s*이수)/g, "$1학점 이상 이수")
    .replace(/\s*\+\s*/g, " 및 ")
    .replace(/\s+그리고\s+/g, " 및 ")
    .replace(/당/g, "에서")
    .replace(/각\s+각/g, "각")
    .replace(/각\s+각/g, "각")
    .replace(/각\s+각/g, "각")
    .replace(/각\s+각/g, "각");

  moduleNames.forEach(moduleName => {
    normalized = normalized.replace(
      new RegExp(`${escapeRegExp(moduleName)}(?=\\s+(?:각|\\d|택|전체|관련|모든))`, "g"),
      `${moduleName}에서`
    );
  });

  return normalized
    .replace(/\s{2,}/g, " ")
    .replace(/\s+및\s+/g, " 및 ")
    .trim();
};

const formatTrackRulesSummary = (
  track: Pick<TrackDetailInfo, "rules_summary" | "module_keys" | "module_names">,
  modules: TrackSummaryModule[] = []
) => {
  const modulePairsFromTrack = (track.module_keys || []).map((key, index) => ({
    key: key.toLowerCase(),
    name: track.module_names?.[index],
  })).filter((module): module is { key: string; name: string } => Boolean(module.key && module.name));

  const modulePairsFromData = modules
    .map(module => ({
      key: module.module_key?.toLowerCase(),
      name: module.module_name,
    }))
    .filter((module): module is { key: string; name: string } => Boolean(module.key && module.name));

  const modulePairs = Array.from(
    new Map([...modulePairsFromTrack, ...modulePairsFromData].map(module => [module.key, module])).values()
  );

  if (modulePairs.length === 0) {
    return condenseRuleSummary(normalizeRuleSummaryText(track.rules_summary?.trim() || buildModuleFallbackSummary(modules, "")));
  }

  const moduleNameByKey = new Map(modulePairs.map(module => [module.key, module.name]));
  const allModuleNameText = modulePairs.map(module => module.name).join(", ");
  const toModuleNames = (codeText: string) => {
    const names = codeText
      .split(/\s*[,+/]\s*/)
      .map(code => moduleNameByKey.get(code.trim().toLowerCase()))
      .filter((name): name is string => Boolean(name));
    return names.length > 0 ? names.join(" 및 ") : codeText;
  };

  const rawSummary = track.rules_summary?.trim();
  if (!rawSummary) return buildModuleFallbackSummary(modules, allModuleNameText);

  const formatted = rawSummary
    .replace(/모듈별/g, "각")
    .replace(/각 모듈/g, "각")
    .replace(/(^|[^A-Za-z가-힣0-9_])([a-z0-9]+(?:\s*[,+/]\s*[a-z0-9]+)*)\s*모듈/gi, (_match, prefix, codes) => {
      const moduleNameText = toModuleNames(codes);
      return `${prefix}${moduleNameText}에서`;
    })
    .replace(/(^|[^A-Za-z가-힣0-9_])([a-z0-9]+(?:\s*[,+/]\s*[a-z0-9]+)*)\s*(?=(중|에서|수강|이수))/gi, (_match, prefix, codes, nextWord) => {
      const moduleNameText = toModuleNames(codes);
      const wasMapped = moduleNameText !== codes;
      return `${prefix}${moduleNameText}${wasMapped && ["수강", "이수"].includes(nextWord) ? "에서 " : ""}`;
    })
    .replace(/모듈/g, allModuleNameText)
    .replace(new RegExp(`^(${modulePairs.map(module => escapeRegExp(module.name)).join("|")})(?=\\s+(?:각|\\d|택|전체|관련))`), "$1에서");

  return condenseRuleSummary(normalizeRuleSummaryText(
    (formatted || buildModuleFallbackSummary(modules, allModuleNameText))
      .replace(new RegExp(`(${modulePairs.map(module => escapeRegExp(module.name)).join("|")})(\\s+및\\s+)(${modulePairs.map(module => escapeRegExp(module.name)).join("|")})(?=\\s+(?:각|각|\\d|택|전체|관련|이수))`), "$1 및 $3에서"),
    modulePairs.map(module => module.name)
  ));
};

class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean; error: Error | null}> {
  constructor(props: {children: React.ReactNode}) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary] 렌더링 에러:", error, info.componentStack);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{padding: '40px', textAlign: 'center'}}>
          <h2>⚠️ 화면 렌더링 중 오류가 발생했습니다.</h2>
          <pre style={{textAlign: 'left', background: '#f5f5f5', padding: '20px', borderRadius: '8px', overflow: 'auto', maxWidth: '600px', margin: '20px auto'}}>
            {this.state.error?.message}
          </pre>
          <button onClick={() => { this.setState({hasError: false, error: null}); window.location.reload(); }} style={{padding: '10px 20px', fontSize: '16px', cursor: 'pointer'}}>
            새로고침
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function DropdownIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"></circle>
      <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
    </svg>
  );
}

const isAdditionalCheckRule = (rule: RuleResultInfo) => {
  const ruleType = rule.rule_type.toLowerCase();
  const description = rule.description.toLowerCase();
  return (
    rule.evaluation_status === "manual_review" ||
    ruleType.includes("portfolio") ||
    ruleType.includes("raw") ||
    ruleType.includes("manual") ||
    description.includes("수동") ||
    description.includes("범주형")
  );
};

const getAdditionalCheckLabel = (rule: RuleResultInfo, major?: string, trackName?: string) => {
  const ruleType = rule.rule_type.toLowerCase();
  const items = rule.manual_review_items?.filter(Boolean) || [];

  // 사회학과 문화기획 전공트랙
  if (major?.includes("사회") && trackName?.includes("문화기획")) {
    return "비교과 프로그램 참여/수료";
  }

  if (ruleType.includes("portfolio")) {
    const count = rule.required_value || rule.shortage_count || 1;
    return `포트폴리오 ${count}건 이상`;
  }

  if (items.length > 0) {
    return items.length === 1 ? items[0] : `${items[0]} 외 ${items.length - 1}건`;
  }

  if (rule.description.includes("범주형")) {
    return "가이드북 별도 조건 확인";
  }

  return "이수 조건";
};

const getAdditionalCheckHelp = (rule: RuleResultInfo, major?: string, trackName?: string) => {
  // 사회학과 문화기획 전공트랙
  if (major?.includes("사회") && trackName?.includes("문화기획")) {
    return "대상: 인턴십, 멘토링, 워크숍 등\n인정 범위: 학과·중앙동아리·지자체·중앙정부 주관 프로그램";
  }

  if (rule.rule_type.toLowerCase().includes("portfolio")) {
    return "성적표 과목만으로는 확인할 수 없는 포트폴리오 제출 조건입니다. 제출·보유 건수를 함께 확인해주세요.";
  }

  if (rule.note) {
    return rule.note;
  }

  const items = rule.manual_review_items?.filter(Boolean) || [];
  if (items.length > 0) {
    return items.join(" / ");
  }

  return "가이드북 또는 학과 사무실을 통해 직접 확인해주세요.";
};

const formatRuleDescription = (description: string) =>
  description
    .replace(/\s*\(\d+과목\)\s*$/, "")
    .replace(/필수\s*과목\s*범주\s*\((?:[^()]*|\([^()]*\))*\)/g, "필수 과목 범주")
    .replace(/필수\s*과목\s*범주\s*\)/g, "필수 과목 범주")
    .replace(/필수\s*과목\s*범주\s+확인/g, "필수 과목 범주 이수")
    .replace(/필수\s*과목\s*\((?:[^()]*|\([^()]*\))*\)/g, "필수 과목")
    .replace(/필수\s*과목\s*\)/g, "필수 과목")
    .replace(/'[^']*'\s*모듈\s+\d+(?:,\s*\d+)*번\s*과목(?:\([^)]+\))?\s*이수/g, "필수 과목 이수")
    .replace(/'([^']*)'\s*모듈\s+전\s*과목\s*이수/g, "$1 모든 과목 이수")
    .replace(/'([^']*)'\s*모듈에서/g, "'$1'에서")
    .replace(/필수\s*과목\s+외\s+트랙\s+내\s+추가/g, "추가");

interface SearchableSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: { deptName?: string; courses?: string[]; label?: string; value?: string }[];
  placeholder: string;
  className?: string;
  style?: React.CSSProperties;
  headerExtra?: React.ReactNode;
}

function SearchableSelect({ value, onChange, options, placeholder, className, style, headerExtra }: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selectId = useRef(`searchable-select-${Math.random().toString(36).slice(2)}`);
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: 300 });

  const updateMenuPosition = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const spaceBelow = window.innerHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const maxHeight = Math.min(300, Math.max(180, Math.max(spaceBelow, spaceAbove)));
    const openAbove = spaceBelow < 180 && spaceAbove > spaceBelow;
    setMenuPosition({
      top: openAbove ? Math.max(8, rect.top - maxHeight - 4) : rect.bottom + 4,
      left: rect.left,
      width: rect.width,
      maxHeight,
    });
  };

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const detail = (event as CustomEvent<string>).detail;
      if (detail !== selectId.current) {
        setIsOpen(false);
      }
    };
    window.addEventListener("searchable-select-open", handleOpen);
    window.addEventListener("select-menu-open", handleOpen);
    return () => {
      window.removeEventListener("searchable-select-open", handleOpen);
      window.removeEventListener("select-menu-open", handleOpen);
    };
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    updateMenuPosition();
    window.addEventListener("scroll", updateMenuPosition, true);
    window.addEventListener("resize", updateMenuPosition);
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) { setIsOpen(false); setSearch(""); }
    }, { threshold: 0 });
    if (triggerRef.current) observer.observe(triggerRef.current);
    return () => {
      window.removeEventListener("scroll", updateMenuPosition, true);
      window.removeEventListener("resize", updateMenuPosition);
      observer.disconnect();
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (triggerRef.current?.contains(target)) return;
      if (target.closest(`[data-select-id="${selectId.current}"]`)) return;
      setIsOpen(false);
      setSearch("");
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setIsOpen(false); setSearch(""); }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const filteredOptions = options.map(opt => {
    if (opt.deptName) {
      const deptMatch = opt.deptName.toLowerCase().includes(search.toLowerCase());
      return {
        ...opt,
        courses: deptMatch
          ? opt.courses
          : opt.courses?.filter(c => c.toLowerCase().includes(search.toLowerCase()))
      };
    }
    return opt.label?.toLowerCase().includes(search.toLowerCase()) ? opt : null;
  }).filter(opt => opt !== null && (opt.deptName ? (opt.courses?.length ?? 0) > 0 : true));

  return (
    <div className="select-wrap" style={{ position: 'relative', width: '100%', ...style }}>
      <div
        ref={triggerRef}
        className={`${className} ${!value ? 'placeholder-select' : ''}`}
        onClick={() => {
          const nextOpen = !isOpen;
          if (nextOpen) {
            updateMenuPosition();
            window.dispatchEvent(new CustomEvent("searchable-select-open", { detail: selectId.current }));
            window.dispatchEvent(new CustomEvent("select-menu-open", { detail: selectId.current }));
          }
          setIsOpen(nextOpen);
        }}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: '16px' }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: 'left', flex: 1 }}>
          {value || placeholder}
        </span>
        <DropdownIcon />
      </div>

      {isOpen && (
        <div className="searchable-select-dropdown" data-select-id={selectId.current} style={{
          position: 'fixed', top: `${menuPosition.top}px`, left: `${menuPosition.left}px`, width: `${menuPosition.width}px`, zIndex: 1000,
          background: 'white', borderRadius: '12px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.1)', border: '1px solid #e5e7eb',
          maxHeight: `${menuPosition.maxHeight}px`, overflowY: 'auto', padding: '8px'
        }}>
          <div style={{ position: 'relative', marginBottom: '8px' }}>
            <div style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}>
              <SearchIcon />
            </div>
            <input
              type="text"
              autoFocus
              placeholder="검색어 입력..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              style={{
                width: '100%', padding: '8px 8px 8px 32px', borderRadius: '8px',
                border: '1px solid #e2e8f0', outline: 'none', fontSize: '16px'
              }}
            />
          </div>

          {headerExtra && (
            <div
              className="searchable-select-header-extra"
              onClick={(e) => e.stopPropagation()}
            >
              {headerExtra}
            </div>
          )}

          <div className="searchable-select-dropdown-inner" style={{ maxHeight: `${Math.max(120, menuPosition.maxHeight - (headerExtra ? 96 : 58))}px`, overflowY: 'auto' }}>
            {filteredOptions.length === 0 ? (
              <div style={{ padding: '12px', textAlign: 'center', color: '#94a3b8', fontSize: '16px' }}>검색 결과가 없습니다.</div>
            ) : (
              filteredOptions.map((opt: any, i) => (
                <div key={i}>
                  {opt.deptName ? (
                    <>
                      <div style={{ padding: '6px 8px', fontSize: '12px', fontWeight: 800, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {opt.deptName}
                      </div>
                      {opt.courses.map((c: string) => (
                        <div
                          key={c}
                          className="select-option"
                          onClick={(e) => { e.stopPropagation(); onChange(c); setIsOpen(false); setSearch(""); }}
                          style={{
                            padding: '9px 12px', cursor: 'pointer', borderRadius: '6px',
                            fontSize: '15px', color: '#374151', transition: 'background 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.background = '#f5f8ff'}
                          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                        >
                          {c}
                        </div>
                      ))}
                    </>
                  ) : (
                    <div
                      className="select-option"
                      onClick={(e) => { e.stopPropagation(); onChange(opt.value); setIsOpen(false); setSearch(""); }}
                      style={{
                        padding: '8px 12px', cursor: 'pointer', borderRadius: '6px',
                        fontSize: '15px', color: '#334155', transition: 'background 0.2s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = '#f5f8ff'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      {opt.label}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface SimpleSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder: string;
  className?: string;
}

function SimpleSelect({ value, onChange, options, placeholder, className }: SimpleSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectId = useRef(`simple-select-${Math.random().toString(36).slice(2)}`);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: 220 });

  const updateMenuPosition = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const spaceBelow = window.innerHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const maxHeight = Math.min(220, Math.max(128, Math.max(spaceBelow, spaceAbove)));
    const openAbove = spaceBelow < 128 && spaceAbove > spaceBelow;
    setMenuPosition({
      top: openAbove ? Math.max(8, rect.top - maxHeight - 4) : rect.bottom + 4,
      left: rect.left,
      width: rect.width,
      maxHeight,
    });
  };

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const detail = (event as CustomEvent<string>).detail;
      if (detail !== selectId.current) {
        setIsOpen(false);
      }
    };
    window.addEventListener("select-menu-open", handleOpen);
    return () => window.removeEventListener("select-menu-open", handleOpen);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    updateMenuPosition();
    window.addEventListener("scroll", updateMenuPosition, true);
    window.addEventListener("resize", updateMenuPosition);
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) setIsOpen(false);
    }, { threshold: 0 });
    if (triggerRef.current) observer.observe(triggerRef.current);
    return () => {
      window.removeEventListener("scroll", updateMenuPosition, true);
      window.removeEventListener("resize", updateMenuPosition);
      observer.disconnect();
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (triggerRef.current?.contains(target)) return;
      if (target.closest(`[data-select-id="${selectId.current}"]`)) return;
      setIsOpen(false);
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  return (
    <div className="select-wrap simple-select-wrap">
      <button
        ref={triggerRef}
        type="button"
        className={`${className || ""} simple-select-button ${!value ? "placeholder-select" : ""}`}
        onClick={() => {
          const nextOpen = !isOpen;
          if (nextOpen) {
            updateMenuPosition();
            window.dispatchEvent(new CustomEvent("select-menu-open", { detail: selectId.current }));
            window.dispatchEvent(new CustomEvent("searchable-select-open", { detail: selectId.current }));
          }
          setIsOpen(nextOpen);
        }}
      >
        <span>{value || placeholder}</span>
        <DropdownIcon />
      </button>

      {isOpen && (
        <div
          className="simple-select-menu"
          data-select-id={selectId.current}
          style={{
            top: `${menuPosition.top}px`,
            left: `${menuPosition.left}px`,
            minWidth: `${menuPosition.width}px`,
            maxHeight: `${menuPosition.maxHeight}px`,
          }}
        >
          {options.map(option => (
            <button
              key={option}
              type="button"
              className="simple-select-option"
              onClick={() => {
                onChange(option);
                setIsOpen(false);
              }}
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StepIndicator({ currentPage }: { currentPage: string; onNavigate?: (stepId: number) => void; maxReachedStep?: number }) {
  const steps = [
    { id: 1, label: "기본 정보", pages: ["info"] },
    { id: 2, label: "입력 방식", pages: ["method", "trackExplore"] },
    { id: 3, label: "과목 확인", pages: ["checklist", "manual"] },
    { id: 4, label: "결과", pages: ["trackList", "trackResult"] },
  ];

  const currentStep = steps.find(s => s.pages.includes(currentPage))?.id || 1;
  if (currentStep === 1) return null;

  return (
    <div className="bottom-step-indicator" aria-label="진행 단계">
      <span className="bottom-step-brand">
        <img src={logo} alt="한림대학교 로고" />
        <span>전공트랙 진단</span>
      </span>
      <span className="bottom-step-count">
        {currentStep - 1} / 3
      </span>
    </div>
  );
}

function App() {
  const [selectedMajors, setSelectedMajors] = useState<string[]>([]);
  const [majorDraft, setMajorDraft] = useState("");
  const [page, setPage] = useState<"info" | "method" | "trackExplore" | "checklist" | "manual" | "trackList" | "trackResult">("info");
  const [previousTrackPage, setPreviousTrackPage] = useState<"checklist" | "manual">("checklist");

  const [courses, setCourses] = useState<Course[]>([{ id: 1, name: "", credit: "3", grade: "이수" }]);

  // API Data States
  const [colleges, setColleges] = useState<CollegeGroup[]>([]);
  const [deptAnalyses, setDeptAnalyses] = useState<DeptAnalysisBundle[]>([]);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [expandedResultGroups, setExpandedResultGroups] = useState<Record<string, boolean>>({
    close: false,
    review: false,
    unrelated: false,
  });
  const [maxReachedStep, setMaxReachedStep] = useState(1);
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const [expandedAdditional, setExpandedAdditional] = useState<Set<number>>(new Set());
  const [moduleCourses, setModuleCourses] = useState<{name: string, credits: number, note?: string}[]>([]);
  const [selectedDeptTracks, setSelectedDeptTracks] = useState<DeptTracksResponse[]>([]);
  const [checkedCourseNames, setCheckedCourseNames] = useState<Set<string>>(new Set());
  const [checklistDeptFilter, setChecklistDeptFilter] = useState<string | null>(null);
  const [trackExploreDeptFilter, setTrackExploreDeptFilter] = useState<string | null>(null);
  const [selectedExploreTrackId, setSelectedExploreTrackId] = useState<string | null>(null);
  const [allDeptCourses, setAllDeptCourses] = useState<{deptName: string, courses: string[]}[]>([]);
  const allCourseCreditsRef = useRef<Map<string, number>>(new Map());

  const [showCourseInfoTip, setShowCourseInfoTip] = useState(false);
  const [showTrackInfoTip, setShowTrackInfoTip] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeMobileTooltip, setActiveMobileTooltip] = useState<string | null>(null);
  const [isMissingCoursesExpanded, setIsMissingCoursesExpanded] = useState(false);
  const [majorLimitMessage, setMajorLimitMessage] = useState("");
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [floatingTooltip, setFloatingTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  const showFeedback = (message: string) => {
    window.alert(message);
  };

  const renderCardLogo = (alt = "로고") => (
    <div className="card-logo-wrap">
      <div className="card-logo-button">
        <img src={logo} alt={alt} className="card-logo" />
      </div>
    </div>
  );

  const resetAnalysis = () => {
    setDeptAnalyses([]);
    setSelectedTrackId(null);
    setExpandedModules(new Set());
    setExpandedAdditional(new Set());
    if (page === "trackList" || page === "trackResult") {
      setPage(previousTrackPage);
    }
  };

  const addSelectedMajor = (value = majorDraft) => {
    const deptName = value.trim();
    if (!deptName || selectedMajors.includes(deptName)) return;
    if (selectedMajors.length >= MAX_SELECTED_MAJORS) {
      setMajorLimitMessage("학과 욕심은 잠시 내려두고, 최대 4개까지만 골라주세요.");
      return;
    }
    setMajorLimitMessage("");
    setSelectedMajors(prev => [...prev, deptName]);
    setMajorDraft("");
    resetAnalysis();
  };

  const removeSelectedMajor = (deptName: string) => {
    setMajorLimitMessage("");
    setSelectedMajors(prev => prev.filter(item => item !== deptName));
    resetAnalysis();
  };

  const toggleMobileTooltip = (tooltipId: string, event: React.SyntheticEvent) => {
    event.stopPropagation();
    setActiveMobileTooltip(prev => prev === tooltipId ? null : tooltipId);
  };

  useEffect(() => {
    setIsMissingCoursesExpanded(false);
  }, [selectedTrackId]);

  useEffect(() => {
    if (!activeMobileTooltip) return;
    const handler = () => setActiveMobileTooltip(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [activeMobileTooltip]);

  const isTouchLikePointer = () =>
    typeof window !== "undefined" && window.matchMedia("(hover: none), (pointer: coarse)").matches;

  useEffect(() => {
    fetchDeptList().then(res => {
      if (res && res.success) {
        setColleges(res.colleges || []);
      }
    }).catch(e => console.error("Failed to load dept list:", e));
  }, []);

  // 모든 학과의 과목을 한번에 불러와서 과목 선택 드롭다운에 사용
  useEffect(() => {
    if (colleges.length === 0) return;
    const allDepts = colleges.flatMap(c => c.departments);
    Promise.all(allDepts.map(d => fetchDeptTracks(d.dept_name).catch(() => null)))
      .then(results => {
        const creditsMap = allCourseCreditsRef.current;
        const grouped = results.map((res, i) => {
          if (!res || !res.success) return { deptName: allDepts[i].dept_name, courses: [] as string[] };
          const courseNames = new Set<string>();
          res.modules.forEach(m => m.courses.forEach(c => {
            courseNames.add(c.course_name);
            if (c.credits) creditsMap.set(c.course_name, c.credits);
          }));
          return { deptName: allDepts[i].dept_name, courses: Array.from(courseNames) };
        }).filter(g => g.courses.length > 0);
        setAllDeptCourses(grouped);
      });
  }, [colleges]);

  useEffect(() => {
    if (selectedMajors.length === 0) {
      setModuleCourses([]);
      setSelectedDeptTracks([]);
      setCheckedCourseNames(new Set());
      setChecklistDeptFilter(null);
      setTrackExploreDeptFilter(null);
      setSelectedExploreTrackId(null);
      return;
    }
    setChecklistDeptFilter(prev => prev && selectedMajors.includes(prev) ? prev : null);
    setTrackExploreDeptFilter(prev => prev && selectedMajors.includes(prev) ? prev : null);

    Promise.all(selectedMajors.map(deptName => fetchDeptTracks(deptName).catch(() => null)))
      .then(results => {
        const coursesMap = new Map<string, { credits: number; note?: string }>();
        const validResults = results.filter((res): res is DeptTracksResponse => Boolean(res && res.success));
        validResults.forEach(res => {
          res.modules.forEach(m => {
            m.courses.forEach(c => {
              if (!coursesMap.has(c.course_name)) {
                coursesMap.set(c.course_name, { credits: c.credits, note: c.note });
              }
            });
          });
        });
        setSelectedDeptTracks(validResults);
        setModuleCourses(Array.from(coursesMap.entries()).map(([name, data]) => ({ name, credits: data.credits, note: data.note })));
        setCheckedCourseNames(prev => new Set(Array.from(prev).filter(name => coursesMap.has(name))));
      })
      .catch(e => console.error("Failed to load selected department courses:", e));
  }, [selectedMajors]);

  const pageToStep = (p: string) => {
    if (p === "method" || p === "trackExplore") return 2;
    if (p === "checklist" || p === "manual") return 3;
    if (p === "trackList" || p === "trackResult") return 4;
    return 1;
  };

  useEffect(() => {
    const step = pageToStep(page);
    setMaxReachedStep(prev => Math.max(prev, step));
  }, [page]);

  const pageStepName: Record<string, string> = {
    info: "start", method: "method", trackExplore: "track-explore", checklist: "checklist", manual: "manual",
    trackList: "tracks", trackResult: "result",
  };
  const stepNameToPage: Record<string, typeof page> = {
    start: "info", method: "method", "track-explore": "trackExplore", checklist: "checklist", manual: "manual",
    upload: "checklist", confirm: "checklist",
    tracks: "trackList", result: "trackResult",
  };
  const isPopstateNavRef = useRef(false);

  useEffect(() => {
    window.history.replaceState({ step: pageStepName[page] }, '', '?step=' + pageStepName[page]);
    const handlePopstate = (event: PopStateEvent) => {
      const step = event.state?.step || new URLSearchParams(window.location.search).get('step') || 'start';
      const targetPage = stepNameToPage[step];
      if (targetPage) { isPopstateNavRef.current = true; setPage(targetPage); }
    };
    window.addEventListener('popstate', handlePopstate);
    return () => window.removeEventListener('popstate', handlePopstate);
  }, []);

  useEffect(() => {
    if (isPopstateNavRef.current) { isPopstateNavRef.current = false; return; }
    window.history.pushState({ step: pageStepName[page] }, '', '?step=' + pageStepName[page]);
  }, [page]);

  useEffect(() => {
    setExpandedModules(new Set());
    setExpandedAdditional(new Set());
  }, [selectedTrackId]);

  const handleStart = () => {
    if (selectedMajors.length === 0) {
      showFeedback("학과를 하나 이상 선택해주세요.");
      return;
    }
    setPage("method");
  };

  const addCourseRow = () => setCourses([...courses, { id: Date.now(), name: "", credit: "3", grade: "이수" }]);
  const removeCourseRow = (id: number) => {
    if (courses.length > 1) setCourses(courses.filter(c => c.id !== id));
  };

  const lookupCredit = (name: string): string | null => {
    const fromModule = moduleCourses.find(mc => mc.name === name);
    if (fromModule) return String(fromModule.credits);
    const fromAll = allCourseCreditsRef.current.get(name);
    if (fromAll) return String(fromAll);
    return null;
  };

  const updateCourse = (id: number, field: "name" | "credit" | "grade", value: string) => {
    setCourses(courses.map(c => {
      if (c.id === id) {
        const updated = { ...c, [field]: value };
        if (field === "name") {
          const credit = lookupCredit(value);
          if (credit) updated.credit = credit;
        }
        return updated;
      }
      return c;
    }));
  };

  const toggleChecklistCourse = (courseName: string) => {
    setCheckedCourseNames(prev => {
      const next = new Set(prev);
      if (next.has(courseName)) next.delete(courseName);
      else next.add(courseName);
      return next;
    });
  };

  const getCourseNote = (courseName: string, fallbackNote?: string) =>
    fallbackNote || moduleCourses.find(course => course.name === courseName)?.note;

  const renderNoteIcon = (tooltipId: string, note?: string) => {
    if (!note) return null;
    return (
      <span
        className={`chip-note-wrap ${activeMobileTooltip === tooltipId ? "tooltip-open" : ""}`}
        role="button"
        tabIndex={0}
        onMouseEnter={(e) => {
          if (isTouchLikePointer()) return;
          const rect = e.currentTarget.getBoundingClientRect();
          setFloatingTooltip({ x: rect.left + rect.width / 2, y: rect.top - 8, text: note });
        }}
        onMouseLeave={() => setFloatingTooltip(null)}
        onClick={(event) => toggleMobileTooltip(tooltipId, event)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") toggleMobileTooltip(tooltipId, event);
        }}
      >
        ⚠️<span className="chip-note-tooltip">{note}</span>
      </span>
    );
  };

  const getChecklistCourses = (): Course[] => {
    const metaMap = new Map<string, { credits: number }>();
    selectedDeptTracks.forEach(dept => {
      dept.modules.forEach(module => {
        module.courses.forEach(course => {
          if (!metaMap.has(course.course_name)) {
            metaMap.set(course.course_name, { credits: course.credits || 3 });
          }
        });
      });
    });

    return Array.from(checkedCourseNames).map((name, index) => ({
      id: index + 1,
      name,
      credit: String(metaMap.get(name)?.credits || lookupCredit(name) || 3),
      grade: "이수",
    }));
  };

  const runAnalysis = async (inputCourses: Course[]) => {
    const validCourses = inputCourses.filter(c => c.name.trim() !== "" && c.credit !== "");
    if (validCourses.length === 0) {
      showFeedback("이수한 과목 정보를 최소 1개 이상 입력해주세요.");
      return false;
    }
    if (selectedMajors.length === 0) {
      showFeedback("분석할 학과를 하나 이상 선택해주세요.");
      return false;
    }

    setLoading(true);
    try {
      const gradeMap: Record<string, string> = {
        "F아님": "A0",
        "이수": "A0",
        "F": "F",
        "Pass": "P",
        "Non-pass": "NP"
      };

      const payload: AnalyzeCourseInput[] = validCourses.map(c => ({
        course_name: c.name.trim(),
        credits: parseInt(c.credit) || 3,
        grade: gradeMap[c.grade] || c.grade || "A0"
      }));

      console.log("[runAnalysis] 분석 요청 시작:", selectedMajors);
      const bundles = await Promise.all(
        selectedMajors.map(async (deptName) => {
          const [resAnalyze, resTracks] = await Promise.all([
            analyzeTrack(deptName, payload),
            fetchDeptTracks(deptName),
          ]);
          return { deptName, analyzeResult: resAnalyze, tracksData: resTracks };
        })
      );

      setDeptAnalyses(bundles);

      const trackCandidates = bundles
        .flatMap(bundle =>
          bundle.analyzeResult.track_results.map(result => ({
            uniqueId: `${bundle.deptName}::${result.track_id}`,
            result,
          }))
        )
        .sort((a, b) => {
          if (a.result.is_completed !== b.result.is_completed) return a.result.is_completed ? -1 : 1;
          if (a.result.completion_rate !== b.result.completion_rate) return b.result.completion_rate - a.result.completion_rate;
          return a.result.additional_required_courses - b.result.additional_required_courses;
        });

      const firstTrackId = bundles[0]?.tracksData.tracks?.[0]?.track_id
        ? `${bundles[0].deptName}::${bundles[0].tracksData.tracks[0].track_id}`
        : null;
      setSelectedTrackId(trackCandidates[0]?.uniqueId || firstTrackId);
      return true;
    } catch (e: any) {
      console.error("[runAnalysis] 에러:", e);
      showFeedback(e?.message || "분석 중 문제가 발생했습니다.\n잠시 후 다시 시도해주세요.");
      return false;
    } finally {
      setLoading(false);
    }
  };

  const goToTrackList = async (from: "checklist" | "manual") => {
    if (from === "checklist" && checkedCourseNames.size === 0) {
      showFeedback("과목을 하나 이상 선택해주세요.");
      return;
    }

    const sourceCourses = from === "checklist" ? getChecklistCourses() : courses;
    const cleanedCourses = sourceCourses.filter(c => c.name.trim() !== "" && c.credit !== "");
    const success = await runAnalysis(cleanedCourses);
    if (success) {
      if (from === "manual") {
        setCourses(cleanedCourses);
      }
      setPreviousTrackPage(from);
      setPage("trackList");
    }
  };

  const departmentOptions = colleges.flatMap(c =>
    c.departments.map(d => ({ label: d.dept_name, value: d.dept_name }))
  );

const renderSelectedDepartments = (
  filterable = false,
  activeDept: string | null = checklistDeptFilter,
  onSelectDept: (deptName: string | null) => void = setChecklistDeptFilter
) => {
  const currentDept = filterable ? activeDept : null;
  const handleSelectDept = filterable ? onSelectDept : undefined;
  return (
    <div className="student-summary department-summary selected-dept-summary">
      <div className="student-summary-title">선택 학과</div>
      <div className="selected-dept-chip-list">
        {filterable && selectedMajors.length > 1 && (
          <button
            type="button"
            className={`selected-dept-chip selected-dept-filter-chip selected-dept-all-chip ${currentDept === null ? "active" : ""}`}
            onClick={() => handleSelectDept?.(null)}
          >
            전체
          </button>
        )}
        {selectedMajors.map((deptName, index) => (
          filterable ? (
            <button
              type="button"
              key={deptName}
              className={`selected-dept-chip selected-dept-filter-chip ${currentDept === deptName ? "active" : ""}`}
              style={getMajorColorStyle(index + 1)}
              onClick={() => handleSelectDept?.(deptName)}
            >
              {formatDeptName(deptName)}
            </button>
          ) : (
            <span key={deptName} className="selected-dept-chip">
              {formatDeptName(deptName)}
            </span>
          )
        ))}
      </div>
    </div>
  );
};

  // 직접 입력은 선택 학과 과목만 사용합니다.
  const selectedDeptCourses = allDeptCourses.filter(g => selectedMajors.includes(g.deptName));
  const manualCourseDropdownOptions = selectedDeptCourses;
  const visibleChecklistDeptTracks = checklistDeptFilter
    ? selectedDeptTracks.filter(dept => dept.dept_name === checklistDeptFilter)
    : selectedDeptTracks;
  const getTrackModules = (track: CombinedTrackInfo, sources: DeptTracksResponse[] = selectedDeptTracks) => {
    const dept = sources.find(source => source.dept_name === track.dept_name);
    if (!dept) return [];
    return track.module_keys
      .map(moduleKey => dept.modules.find(module => module.module_key === moduleKey))
      .filter((module): module is TrackSummaryModule => Boolean(module));
  };
  const exploreTrackEntries: CombinedTrackInfo[] = selectedDeptTracks.flatMap(dept =>
    dept.tracks.map(track => ({
      ...track,
      dept_name: dept.dept_name,
      unique_id: `${dept.dept_name}::${track.track_id}`,
    }))
  );
  const visibleExploreTrackEntries = trackExploreDeptFilter
    ? exploreTrackEntries.filter(track => track.dept_name === trackExploreDeptFilter)
    : exploreTrackEntries;
  const selectedExploreTrack =
    visibleExploreTrackEntries.find(track => track.unique_id === selectedExploreTrackId) ||
    visibleExploreTrackEntries[0] ||
    null;
  const selectedExploreModules = selectedExploreTrack ? getTrackModules(selectedExploreTrack) : [];

  // Computed data for multi-department results
  const allTracks: CombinedTrackInfo[] = deptAnalyses.flatMap(bundle =>
    bundle.tracksData.tracks.map(track => ({
      ...track,
      dept_name: bundle.deptName,
      unique_id: `${bundle.deptName}::${track.track_id}`,
    }))
  );
  const allTrackResults: CombinedTrackResultInfo[] = deptAnalyses.flatMap(bundle =>
    bundle.analyzeResult.track_results.map(result => ({
      ...result,
      dept_name: bundle.deptName,
      unique_id: `${bundle.deptName}::${result.track_id}`,
    }))
  );
  const trackResultsMap = new Map(allTrackResults.map(t => [t.unique_id, t]));
  const rankedTrackEntries = allTracks
    .map(track => ({ track, result: trackResultsMap.get(track.unique_id) }))
    .sort((a, b) => {
      const ar = a.result;
      const br = b.result;
      if (Boolean(ar?.is_completed) !== Boolean(br?.is_completed)) return ar?.is_completed ? -1 : 1;
      const aRate = ar?.completion_rate ?? 0;
      const bRate = br?.completion_rate ?? 0;
      if (aRate !== bRate) return bRate - aRate;
      return (ar?.additional_required_courses ?? 999) - (br?.additional_required_courses ?? 999);
    });
  const hasAnalysis = deptAnalyses.length > 0;

  const getDeptColorStyle = (deptName: string): React.CSSProperties => {
    const deptIndex = selectedMajors.indexOf(deptName);
    return getMajorColorStyle(deptIndex + 1);
  };

  const getTrackStatus = (result?: CombinedTrackResultInfo) => {
    if (!result || result.completion_rate <= 0) return "unrelated";
    if (result.is_completed || result.completion_rate >= 1.0) return "eligible";
    return "partial";
  };
  const getTrackStatusLabel = (result?: CombinedTrackResultInfo) => {
    if (result?.is_completed) return "이수완료";
    const status = getTrackStatus(result);
    if (status === "eligible") return "충족 완료";
    if (status === "partial") return "추천후보";
    return "후순위";
  };
  const getTrackBadgeLabel = (result?: CombinedTrackResultInfo) => {
    if (result?.is_completed || (result?.completion_rate ?? 0) >= 1) return "이수완료";
    if (!result || result.completion_rate <= 0) return "후순위";
    if (result.completion_rate >= 0.5 || result.additional_required_courses <= 2) return "추가 이수 필요";
    return "추천후보";
  };
  const getTrackBadgeTone = (result?: CombinedTrackResultInfo) => {
    if (result?.is_completed || (result?.completion_rate ?? 0) >= 1) return "complete";
    if (!result || result.completion_rate <= 0) return "low";
    if (result.completion_rate >= 0.5 || result.additional_required_courses <= 2) return "need";
    return "candidate";
  };
  const getProgressBadgeLabel = (result?: CombinedTrackResultInfo) => {
    if (result?.is_completed || (result?.completion_rate ?? 0) >= 1) return "이수완료";
    if (!result || result.completion_rate <= 0) return "도전 시작";
    return "도전중";
  };
  const getTrackRankTone = (index: number) => {
    if (index === 0) return "first";
    if (index === 1) return "second";
    if (index === 2) return "third";
    if (index <= 4) return "upper";
    return "default";
  };
  const getTrackRankLabel = (index: number) => `${index + 1}위`;
  const trackRankIndexMap = new Map(rankedTrackEntries.map((entry, index) => [entry.track.unique_id, index]));
  const topRankedTrackEntries = rankedTrackEntries.slice(0, 3);
  const remainingRankedTrackEntries = rankedTrackEntries.slice(3);

  const completedGroupEntries = rankedTrackEntries.filter(entry => entry.result?.is_completed);
  const closeGroupEntries = rankedTrackEntries.filter(entry =>
    !entry.result?.is_completed && getTrackStatus(entry.result) === "eligible"
  );
  const reviewGroupEntries = rankedTrackEntries.filter(entry => getTrackStatus(entry.result) === "partial");
  const unrelatedGroupEntries = rankedTrackEntries.filter(entry => getTrackStatus(entry.result) === "unrelated");
  const resultTrackGroups = [
    { key: "completed", title: "이수완료", description: "이미 조건을 만족한 전공트랙입니다.", entries: completedGroupEntries },
    { key: "close", title: "충족 완료", description: "입력 과목 기준으로 조건을 충족한 전공트랙입니다.", entries: closeGroupEntries },
    { key: "review", title: "추천후보", description: "현재 이수한 과목과 연관성이 높고, 추가 이수를 통해 이어갈 수 있는 전공트랙입니다.", entries: reviewGroupEntries },
    { key: "unrelated", title: "후순위", description: "현재 입력 과목과의 접점이 적어 우선순위가 낮은 전공트랙입니다.", entries: unrelatedGroupEntries },
  ].filter(group => group.entries.length > 0);

  const selectedTrackInfo = allTracks.find(t => t.unique_id === selectedTrackId);
  const selectedResult = trackResultsMap.get(selectedTrackId || "");
  const selectedListStatus = getTrackStatus(selectedResult);
  const selectedListProgress = Math.round((selectedResult?.completion_rate || 0) * 100);
  const selectedRankIndex = selectedTrackId ? trackRankIndexMap.get(selectedTrackId) : undefined;
  const selectedRankTone = selectedRankIndex !== undefined ? getTrackRankTone(selectedRankIndex) : "default";

  const selectedStatus = getTrackStatus(selectedResult);
  const selectedProgressPercent = Math.round((selectedResult?.completion_rate || 0) * 100);
  const selectedAutoRules = selectedResult?.rule_results.filter(r => !isAdditionalCheckRule(r)) || [];
  const selectedSatisfiedRules = selectedAutoRules.filter(r => r.satisfied).length;
  const selectedTotalRuleCount = selectedResult?.total_rules || selectedAutoRules.length;
  const selectedSatisfiedRuleCount = selectedResult?.satisfied_rules ?? selectedSatisfiedRules;
  const selectedRequiredCourses = selectedResult?.additional_required_courses || 0;
  const selectedCandidateCourseCount = selectedResult?.missing_courses.length || 0;
  const selectedRuleSummary = selectedTotalRuleCount > 0
    ? `${selectedSatisfiedRuleCount}/${selectedTotalRuleCount}조건 충족`
    : "조건 확인 중";
  const selectedRequirementSummary = selectedResult?.is_completed
    ? "추가 이수 없음"
    : `최소 ${selectedRequiredCourses}과목, 총 ${selectedCandidateCourseCount}개`;
  const selectedStatusDescription = selectedResult?.is_completed
    ? "트랙 이수 조건을 모두 만족했습니다."
    : selectedRequiredCourses > 0
      ? `후보 과목 ${selectedCandidateCourseCount}개 중 최소 ${selectedRequiredCourses}과목 추가 이수가 필요합니다.`
      : "관련 조건을 확인하고 다음 이수 계획을 세울 수 있습니다.";
  const selectedDisplayRules = (() => {
    if (!selectedResult) return [];
    const sorted = [
      ...selectedResult.rule_results.filter(r => !isAdditionalCheckRule(r))
        .slice()
        .sort((a, b) => {
          if (a.satisfied !== b.satisfied) return a.satisfied ? -1 : 1;
          const aRate = a.required_value ? Math.min(a.current_value / a.required_value, 1) : 0;
          const bRate = b.required_value ? Math.min(b.current_value / b.required_value, 1) : 0;
          return bRate - aRate;
        }),
      ...selectedResult.rule_results.filter(r => isAdditionalCheckRule(r)),
    ];
    // 같은 설명인 규칙을 모두 하나로 병합 (연속 여부 무관)
    const nonAdditional = sorted.filter(r => !isAdditionalCheckRule(r));
    const additional = sorted.filter(r => isAdditionalCheckRule(r));
    const descOrder: string[] = [];
    const descMap = new Map<string, typeof sorted[0]>();
    for (const r of nonAdditional) {
      const desc = formatRuleDescription(r.description);
      if (descMap.has(desc)) {
        const prev = descMap.get(desc)!;
        descMap.set(desc, {
          ...prev,
          satisfied: prev.satisfied && r.satisfied,
          current_value: prev.current_value + r.current_value,
          required_value: prev.required_value + r.required_value,
          shortage_count: (prev.shortage_count || 0) + (r.shortage_count || 0),
          taken_courses: [...(prev.taken_courses || []), ...(r.taken_courses || [])],
          remaining_courses: [...(prev.remaining_courses || []), ...(r.remaining_courses || [])],
          missing_courses: [...(prev.missing_courses || []), ...(r.missing_courses || [])],
          taken_course_details: [...(prev.taken_course_details || []), ...(r.taken_course_details || [])],
          remaining_course_details: [...(prev.remaining_course_details || []), ...(r.remaining_course_details || [])],
          missing_course_details: [...(prev.missing_course_details || []), ...(r.missing_course_details || [])],
        });
      } else {
        descMap.set(desc, { ...r });
        descOrder.push(desc);
      }
    }
    // total_min_courses와 track_min_credits가 동시에 존재하면 학점 행은 제거 (6과목=18학점 동일 조건)
    const hasTotalMinCourses = descOrder.some(desc => descMap.get(desc)?.rule_type === "total_min_courses");
    const filteredDescOrder = hasTotalMinCourses
      ? descOrder.filter(desc => descMap.get(desc)?.rule_type !== "track_min_credits")
      : descOrder;
    return [...filteredDescOrder.map(desc => descMap.get(desc)!), ...additional];
  })();

  return (
    <div className="container">
      <div className="background-circle background-circle-1"></div>
      <div className="background-circle background-circle-2"></div>

      {page === "info" && (
        <div className="card info-card">
          {renderCardLogo("한림대학교 로고")}
          <div
            className="intro-title-row"
            onMouseLeave={() => {
              if (!isTouchLikePointer()) setShowTrackInfoTip(false);
            }}
          >
            <h2 className="subtitle main-subtitle">
              <span className="home-title-prefix">학생 맞춤형 </span>
              전공트랙
              <span className="home-title-mobile-break"><br /></span>
              <span className="home-title-desktop-space"> </span>
              진단 시스템
              <button
                type="button"
                className={`track-info-button ${showTrackInfoTip ? "active" : ""}`}
                onMouseEnter={() => {
                  if (!isTouchLikePointer()) setShowTrackInfoTip(true);
                }}
                onClick={() => {
                  if (isTouchLikePointer()) setShowTrackInfoTip(prev => !prev);
                }}
                aria-label="맞춤형 전공트랙 안내"
              >
                ?
              </button>
            </h2>
            {showTrackInfoTip && (
              <div className="track-info-popover">
                <strong>맞춤형 전공트랙이란?</strong>
                <p>선택한 학과와 이수 과목을 기준으로 달성 가능한 전공트랙, 진행률, 보완 과목을 확인하는 기능입니다.</p>
                <ul>
                  <li>관심 학과를 여러 개 선택할 수 있습니다.</li>
                  <li>이수 과목을 체크하면 관련 트랙을 우선 정렬합니다.</li>
                  <li>트랙별 부족한 과목과 조건을 함께 확인합니다.</li>
                </ul>
              </div>
            )}
          </div>
          <p className="description">관심 있는 학과를 1개 이상, 최대 4개까지 선택해주세요.<br/>선택한 학과와 현재 이수 현황을 기준으로 전공트랙을 확인합니다.</p>

          <div className="form-group">
                        <div className="major-add-row">
              <SearchableSelect
                value={majorDraft}
                onChange={setMajorDraft}
                options={departmentOptions.filter(opt => !selectedMajors.includes(opt.value || ""))}
                placeholder="학과를 검색하세요."
                className="input"
              />
              <button
                type="button"
                className="major-add-button"
                onClick={() => addSelectedMajor()}
                disabled={!majorDraft}
              >
                추가
              </button>
            </div>
          </div>

          <div className="selected-major-panel">
            {selectedMajors.length === 0 ? (
              <span className="selected-major-empty">분석할 학과를 하나 이상 추가하세요.</span>
            ) : (
              selectedMajors.map((deptName) => (
                <span
                  key={deptName}
                  className="selected-major-chip"
                  onClick={() => removeSelectedMajor(deptName)}
                  style={{ cursor: 'pointer' }}
                >
                  {formatDeptName(deptName)}
                  <button type="button" onClick={e => { e.stopPropagation(); removeSelectedMajor(deptName); }} aria-label={`${deptName} 삭제`}>×</button>
                </span>
              ))
            )}
          </div>

          {majorLimitMessage && (
            <p className="major-limit-message">{majorLimitMessage}</p>
          )}

          <div className="main-support-links">
            <a
              href="https://www.hallym.ac.kr/hallym/index.do"
              target="_blank"
              rel="noopener noreferrer"
              className="module-track-link"
            >
              한림대학교 홈페이지 →
            </a>
            <span className="main-support-divider"></span>
            <a
              href="https://www.hallym.ac.kr/hallym/1076/subview.do"
              target="_blank"
              rel="noopener noreferrer"
              className="module-track-link"
            >
              모듈형 트랙제 알아보기 →
            </a>
          </div>

          <button className="button" onClick={handleStart}>시작하기</button>
        </div>
      )}

      {page === "method" && (
        <div className="card method-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "manual");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="method-page-title">어떤 방식으로 전공트랙을 확인할까요?</h1>
          <br></br>
          <div className="method-option-stack">
            <button className="method-option method-option-green" onClick={() => setPage("checklist")}>
              <div className="method-icon-wrap green"><ChecklistIcon /></div>
              <div className="method-option-title">이수 과목 체크하기</div>
              <div className="method-option-desc">이수한 과목을 체크해 전공트랙 이수 가능성을 빠르게 확인합니다.</div>
            </button>
            <button className="method-option method-option-blue" onClick={() => setPage("trackExplore")}>
              <div className="method-icon-wrap blue"><TrackExploreIcon /></div>
              <div className="method-option-title">전공트랙 둘러보기</div>
              <div className="method-option-desc">선택한 학과의 전공트랙 조건과<br />관련 과목을 먼저 확인합니다.</div>
            </button>
          </div>
          <button className="sub-button method-back-button" onClick={() => setPage("info")}>이전 단계</button>
        </div>
      )}

      {page === "trackExplore" && (
        <div className="card track-explore-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "checklist");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="manual-page-title">전공트랙 둘러보기</h1>
          <p className="method-page-desc">
            선택한 학과의 전공트랙 조건과 관련 모듈을 확인할 수 있습니다.
            <span className="mobile-text-break"><br /></span>
            <span className="mobile-text-space"> </span>
          </p>
          {renderSelectedDepartments(true, trackExploreDeptFilter, setTrackExploreDeptFilter)}

          <div className="track-explore-layout">
            <div className="track-explore-list" aria-label="전공트랙 목록">
              {visibleExploreTrackEntries.length === 0 ? (
                <div className="track-explore-empty">선택한 학과의 전공트랙 정보를 불러오는 중입니다.</div>
              ) : (
                visibleExploreTrackEntries.map(track => (
                  <button
                    type="button"
                    key={track.unique_id}
                    className={`track-explore-card ${selectedExploreTrack?.unique_id === track.unique_id ? "active" : ""}`}
                    onClick={() => setSelectedExploreTrackId(track.unique_id)}
                  >
                    <div className="track-explore-card-top">
                      <span className="track-icon">{getEmoji(track.track_name)}</span>
                      <strong>{formatTrackName(track.track_name)}</strong>
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="track-explore-detail">
              {selectedExploreTrack ? (
                <>
                  <div className="track-explore-detail-head">
                    <span className="quick-panel-kicker dept-color-chip" style={getDeptColorStyle(selectedExploreTrack.dept_name)}>{formatDeptName(selectedExploreTrack.dept_name)}</span>
                    <h2>{formatTrackName(selectedExploreTrack.track_name)}</h2>
                    <p>{formatTrackRulesSummary(selectedExploreTrack, selectedExploreModules)}</p>
                  </div>
                  <div className="track-explore-module-list">
                    {selectedExploreModules.map(module => (
                      <section className="track-explore-module" key={`${selectedExploreTrack.unique_id}-${module.module_key}`}>
                        <div className="track-explore-module-head">
                          <h3>{module.module_name}</h3>
                          <span>{module.courses.length}과목</span>
                        </div>
                        <div className="track-explore-course-chips">
                          {module.courses.map(course => {
                            const note = getCourseNote(course.course_name, course.note);
                            const tooltipId = `explore-${module.module_key}-${course.course_name}`;
                            return (
                              <span className="track-explore-course-chip" key={`${module.module_key}-${course.course_name}`}>
                                <strong className="track-explore-course-name">{course.course_name}</strong>
                                <small className="track-explore-course-credit">{course.credits || 3}학점</small>
                                {renderNoteIcon(tooltipId, note)}
                              </span>
                            );
                          })}
                        </div>
                      </section>
                    ))}
                  </div>
                </>
              ) : (
                <div className="track-explore-empty">확인할 전공트랙이 없습니다.</div>
              )}
            </div>
          </div>

          <div className="manual-button-group">
            <button className="sub-button" onClick={() => setPage("method")}>이전 단계</button>
            <button
              className="button"
              onClick={() => {
                if (selectedExploreTrack) setChecklistDeptFilter(selectedExploreTrack.dept_name);
                setPage("checklist");
              }}
            >
              과목 체크하러 가기
            </button>
          </div>
        </div>
      )}

      {page === "checklist" && (
        <div className="card checklist-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "checklist");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="manual-page-title">이수 과목 체크하기</h1>
          <p className="method-page-desc">
            선택한 학과의 과목 중 이수한 과목을 체크하면
            <span className="mobile-text-break"><br /></span>
            <span className="mobile-text-space"> </span>
            진단에 자동으로 반영됩니다.
          </p>
          {renderSelectedDepartments(true)}

          <div className="checklist-summary-bar">
            <div>
              <span className="checklist-summary-label">선택 과목</span>
              <strong>{checkedCourseNames.size}개</strong>
            </div>
            <button
              type="button"
              className="checklist-clear-button"
              onClick={() => setCheckedCourseNames(new Set())}
              disabled={checkedCourseNames.size === 0}
            >
              전체 해제
            </button>
          </div>

          <div className="checklist-course-section">
            {selectedDeptTracks.length === 0 ? (
              <div className="checklist-empty">선택한 학과의 과목 정보를 불러오는 중입니다.</div>
            ) : (
              visibleChecklistDeptTracks.map(dept => {
                const deptIndex = selectedMajors.indexOf(dept.dept_name);
                const deptColorStyle = getMajorColorStyle(deptIndex + 1);
                const deptCourses = Array.from(
                  new Map(
                    dept.modules.flatMap(module =>
                      module.courses.map(course => [course.course_name, course])
                    )
                  ).values()
                ).sort((a, b) => a.course_name.localeCompare(b.course_name, "ko-KR"));
                const selectedCount = deptCourses.filter(course => checkedCourseNames.has(course.course_name)).length;

                return (
                  <section className="checklist-dept-group" key={dept.dept_name}>
                    <div className="checklist-dept-title" style={deptColorStyle}>
                      <span className="checklist-dept-title-chip">{formatDeptName(dept.dept_name)}</span>
                    </div>
                    <div className="checklist-module-card checklist-dept-course-card" style={deptColorStyle}>
                      <div className="checklist-module-head checklist-dept-course-head">
                        <h3>전체 과목</h3>
                        <span>{selectedCount}/{deptCourses.length}</span>
                      </div>
                      <div className="checklist-course-grid">
                        {deptCourses.map(course => {
                          const checked = checkedCourseNames.has(course.course_name);
                          return (
                            <label
                              key={`${dept.dept_name}-${course.course_name}`}
                              className={`checklist-course ${checked ? "checked" : ""}`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleChecklistCourse(course.course_name)}
                              />
                              <span className="checklist-course-name">{course.course_name}</span>
                              <span className="checklist-course-credit">{course.credits || 3}학점</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </section>
                );
              })
            )}
          </div>

          <div className="manual-button-group">
            <button className="sub-button" onClick={() => setPage("method")}>이전 단계</button>
            <button className="button" onClick={() => goToTrackList("checklist")} disabled={loading}>
              {loading ? "진단 중입니다..." : "진단 시작하기"}
            </button>
          </div>
        </div>
      )}

      {page === "manual" && (
        <div className="card manual-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "manual");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="manual-page-title">직접 입력</h1>
          <p className="method-page-desc">
            이수한 과목명, 학점, 성적을 입력한 후
            <span className="mobile-text-break"><br /></span>
            <span className="mobile-text-space"> </span>
            진단을 시작하세요.
          </p>
          {renderSelectedDepartments()}

          <div className="course-input-section">
            <div className="mobile-course-info-bar">
              <span>과목/학과명</span>
              <button
                type="button"
                className="info-tooltip-icon mobile-info-btn"
                onClick={() => setShowCourseInfoTip(p => !p)}
                aria-label="안내"
              >?</button>
            </div>
            {showCourseInfoTip && (
              <>
                <div className="mobile-tip-overlay" onClick={() => setShowCourseInfoTip(false)} />
                <div className="mobile-course-info-popup">
                  전공트랙 이수 여부는 트랙 기준에 포함된 과목만 반영됩니다.<br />교양 과목이나 기준 데이터에 없는 과목은 분석 결과에서 제외될 수 있습니다.
                </div>
              </>
            )}
            <div className="manual-header">
              <span className="col-header-with-tooltip">
                과목/학과명
                <span className="info-tooltip-wrap">
                  <span className="info-tooltip-icon">?</span>
                  <div className="info-tooltip-popup">
                    전공트랙 이수 여부는 트랙 기준에 포함된 과목만 반영됩니다.<br />교양 과목이나 기준 데이터에 없는 과목은 분석 결과에서 제외될 수 있습니다.
                  </div>
                </span>
              </span>
              <span>학점</span><span>이수상태</span><span></span>
            </div>
            <div className="manual-course-scroll">
              {courses.map(course => (
                <div className="manual-row" key={course.id}>
                  <div className="select-wrap" data-mobile-label="과목/학과명">
                    <SearchableSelect
                      value={course.name}
                      onChange={(val) => updateCourse(course.id, "name", val)}
                      options={manualCourseDropdownOptions}
                      placeholder="선택한 학과 과목을 검색하세요"
                      className="manual-input course-name"
                    />
                  </div>
                  <div className="select-wrap" data-mobile-label="학점">
                    <SimpleSelect
                      value={course.credit}
                      onChange={(val) => updateCourse(course.id, "credit", val)}
                      options={creditOptions}
                      placeholder="선택"
                      className="manual-input course-credit"
                    />
                  </div>
                  <div className="select-wrap" data-mobile-label="이수상태">
                    <SimpleSelect
                      value={course.grade}
                      onChange={(val) => updateCourse(course.id, "grade", val)}
                      options={gradeOptions}
                      placeholder="선택"
                      className="manual-input course-grade"
                    />
                  </div>
                  <button className="delete-icon" aria-label="과목 삭제" onClick={() => removeCourseRow(course.id)}>×</button>
                </div>
              ))}
            </div>
            <div className="course-input-footer">
              <button className="add-button" onClick={addCourseRow}>+ 과목 추가</button>
            </div>
          </div>
          <datalist id="course-list">
            {moduleCourses.map(c => <option key={c.name} value={c.name} />)}
          </datalist>

          <div className="manual-button-group">
            <button className="sub-button" onClick={() => setPage("method")}>이전 단계</button>
            <button className="button" onClick={() => goToTrackList("manual")} disabled={loading}>
              {loading ? "진단 중입니다..." : "진단 시작하기"}
            </button>
          </div>
        </div>
      )}

      {page === "trackList" && (
        <div className="card track-overview-page track-match-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "manual");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="manual-page-title track-list-title">선택 과목과 가까운 전공트랙</h1>
          <p className="track-list-subtitle">선택한 과목과 관련성이 높은 전공트랙을 우선 정렬했습니다.</p>

          {selectedTrackInfo && (
            <div className={`track-list-quick-panel match-${selectedListStatus} rank-tone-${selectedRankTone}`}>
              <div className="quick-panel-top">
                <div>
                  <span className="quick-panel-kicker dept-color-chip" style={getDeptColorStyle(selectedTrackInfo.dept_name)}>{formatDeptName(selectedTrackInfo.dept_name)}</span>
                  <h3>{formatTrackName(selectedTrackInfo.track_name)}</h3>
                </div>
                <div className="quick-panel-actions">
                  {selectedRankIndex !== undefined && (
                    <span className={`track-rank-chip rank-tone-${selectedRankTone}`}>{getTrackRankLabel(selectedRankIndex)}</span>
                  )}
                  <span className={`track-match-badge match-${selectedListStatus}`}>{getTrackStatusLabel(selectedResult)}</span>
                </div>
              </div>
              <div className="quick-panel-progress">
                <div className="quick-panel-progress-head">
                  <span>입력 과목 기준 진행률</span>
                  <strong>{selectedListProgress}%</strong>
                </div>
                <div className="track-match-progress">
                  <span style={{ width: `${selectedListProgress}%` }} />
                </div>
              </div>
              {selectedResult && selectedResult.missing_courses.length > 0 && (
                <div className="quick-panel-missing">
                  <span>보완 과목</span>
                  <div>
                    {selectedResult.missing_courses.slice(0, 4).map(courseName => {
                      const note = getCourseNote(courseName);
                      return (
                        <span key={courseName} className="quick-missing-chip">
                          {courseName}
                          {renderNoteIcon(`quick-${courseName}`, note)}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="track-section track-list-section">
            <div className="track-section-header">
              <h2 className="track-section-title">전체 전공트랙</h2>
              <span className="track-section-badge">{allTracks.length}개</span>
            </div>
            <div className="track-list-scroll">
              <div className="track-list-top3-grid">
                {topRankedTrackEntries.map(({ track, result }, index) => {
                  const status = getTrackStatus(result);
                  const progressPercent = Math.round((result?.completion_rate || 0) * 100);
                  const rankTone = getTrackRankTone(index);
                  return (
                    <button
                      key={track.unique_id}
                      className={`all-track-card track-match-card track-rank-large-card match-${status} rank-tone-${rankTone} ${selectedTrackId === track.unique_id ? "active" : ""}`}
                      onClick={() => setSelectedTrackId(track.unique_id)}
                    >
                      <div className="track-rank-large-main">
                        <div>
                          <span className="all-track-name">{formatTrackName(track.track_name)}</span>
                          <small>{formatDeptName(track.dept_name)} · 진행률 {progressPercent}%</small>
                        </div>
                      </div>
                      <div className="track-card-meta-row">
                        <span className={`track-rank-chip rank-tone-${rankTone}`}>{getTrackRankLabel(index)}</span>
                        <span className={`track-match-badge match-${status}`}>{getTrackStatusLabel(result)}</span>
                      </div>
                      <div className="track-match-progress">
                        <span style={{ width: `${progressPercent}%` }} />
                      </div>
                    </button>
                  );
                })}
              </div>
              {remainingRankedTrackEntries.length > 0 && (
                <div className="track-list-rest-panel">
                  <div className="track-list-rest-head">
                    <span>나머지 전공트랙</span>
                    <strong>{remainingRankedTrackEntries.length}개</strong>
                  </div>
                  <div className="track-list-rest-list">
                    {remainingRankedTrackEntries.map(({ track, result }, restIndex) => {
                      const index = restIndex + 3;
                      const status = getTrackStatus(result);
                      const progressPercent = Math.round((result?.completion_rate || 0) * 100);
                      const rankTone = getTrackRankTone(index);
                      return (
                        <button
                          key={track.unique_id}
                          className={`track-rest-row match-${status} rank-tone-${rankTone} ${selectedTrackId === track.unique_id ? "active" : ""}`}
                          onClick={() => setSelectedTrackId(track.unique_id)}
                        >
                          <span className={`track-rank-chip rank-tone-${rankTone}`}>{getTrackRankLabel(index)}</span>
                          <span className="track-rest-main">
                            <strong>{formatTrackName(track.track_name)}</strong>
                            <small>{formatDeptName(track.dept_name)}</small>
                          </span>
                          <span className={`track-match-badge match-${status}`}>{getTrackStatusLabel(result)}</span>
                          <b>{progressPercent}%</b>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="manual-button-group">
            <button className="sub-button" onClick={() => setPage(previousTrackPage)}>이전 단계</button>
            <button className="button" onClick={() => setPage("trackResult")}>전체 결과 확인하기</button>
          </div>
        </div>
      )}

      {page === "trackResult" && (
        <div className="card track-overview-page track-result-page">
          <StepIndicator currentPage={page} maxReachedStep={maxReachedStep} onNavigate={(stepId) => {
            if (stepId === 2) setPage("method");
            else if (stepId === 3) setPage(previousTrackPage || "manual");
            else if (stepId === 4 && hasAnalysis) setPage("trackList");
          }} />
          <h1 className="manual-page-title">전체 결과</h1>
          <p className="method-page-desc">트랙별 이수 현황을 확인하고,<span className="mobile-text-break"><br/></span><span className="mobile-text-space"> </span>원하는 트랙을 선택해 상세 결과를 볼 수 있습니다.</p>

          <div className="track-result-layout">
            <div className="track-result-main">
              {rankedTrackEntries.length > 0 && (
                <div className="result-summary-card result-top3-card">
                  <div className="result-top3-heading">
                    <span>전체 학과 기준</span>
                    <h2>추천 TOP 3</h2>
                  </div>
                  <div className="result-top3-list">
                    {rankedTrackEntries
                      .filter(({ result }) => (result?.completion_rate || 0) > 0)
                      .slice(0, 3)
                      .map(({ track, result }, index) => {
                      const status = getTrackStatus(result);
                      const progressPercent = Math.round((result?.completion_rate || 0) * 100);
                      const rankTone = getTrackRankTone(index);
                      const isSelected = selectedTrackId === track.unique_id;
                      return (
                        <button
                          key={track.unique_id}
                          className={`result-top3-item rank-${index + 1} rank-tone-${rankTone} match-${status} status-${getTrackBadgeTone(result)} ${isSelected ? "active" : ""}`}
                          onClick={() => setSelectedTrackId(track.unique_id)}
                          aria-selected={isSelected}
                        >
                          <span className="result-top3-info">
                            <strong>{formatTrackName(track.track_name)}</strong>
                            <small>{formatDeptName(track.dept_name)} · 진행률 {progressPercent}%</small>
                          </span>
                          <span className="result-top3-side">
                            <span className={`result-status-badge status-${getTrackBadgeTone(result)}`}>
                              {getTrackBadgeLabel(result)}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="track-section result-group-section">
                <div className="track-section-header all-result-header">
                  <h2 className="track-section-title">전체 전공트랙 결과</h2>
                  <span className="track-section-badge">{rankedTrackEntries.length}개</span>
                </div>
                <div className="result-group-stack">
                  {resultTrackGroups.map(group => {
                    const isCollapsibleGroup = ["close", "review", "unrelated"].includes(group.key);
                    const isGroupExpanded = !isCollapsibleGroup || expandedResultGroups[group.key] !== false;

                    return (
                      <section className={`result-track-group group-${group.key}`} key={group.key}>
                        <button
                          type="button"
                          className={`result-track-group-head ${isCollapsibleGroup ? "collapsible" : ""} ${isCollapsibleGroup && isGroupExpanded ? "open" : ""}`}
                          onClick={() => {
                            if (!isCollapsibleGroup) return;
                            setExpandedResultGroups(prev => ({
                              ...prev,
                              [group.key]: prev[group.key] === false,
                            }));
                          }}
                        >
                          <div>
                            <h3>
                              {group.title}
                              <span className={`result-track-group-count group-${group.key}`}>{group.entries.length}개</span>
                            </h3>
                            <p>{group.description}</p>
                          </div>
                          {isCollapsibleGroup && (
                            <span className={`result-track-toggle-icon ${isGroupExpanded ? "open" : ""}`}>
                              ▾
                            </span>
                          )}
                        </button>
                        {isGroupExpanded && (
                          <div className="result-track-list">
                            {group.entries.map(({ track, result }) => {
                              const status = getTrackStatus(result);
                              const progressPercent = Math.round((result?.completion_rate || 0) * 100);
                              const rankIndex = trackRankIndexMap.get(track.unique_id) ?? 0;
                              const rankTone = getTrackRankTone(rankIndex);
                              const isSelected = selectedTrackId === track.unique_id;
                              return (
                                <button
                                  key={track.unique_id}
                                  className={`result-track-row match-${status} rank-tone-${rankTone} status-${getTrackBadgeTone(result)} ${isSelected ? "active" : ""}`}
                                  onClick={() => setSelectedTrackId(track.unique_id)}
                                  aria-selected={isSelected}
                                >
                                  <span className="result-track-row-main">
                                    <strong>{formatTrackName(track.track_name)}</strong>
                                    <small>{formatDeptName(track.dept_name)} · {result ? `${result.satisfied_rules}/${result.total_rules}모듈` : `0/${track.module_keys.length}모듈`}</small>
                                  </span>
                                  <span className="result-track-row-side">
                                    <span className={`result-track-rank rank-tone-${rankTone}`}>{getTrackRankLabel(rankIndex)}</span>
                                    <em className={`result-status-badge compact status-${getTrackBadgeTone(result)}`}>{getTrackBadgeLabel(result)}</em>
                                    <b>{progressPercent}%</b>
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </section>
                    );
                  })}
                </div>
              </div>
            </div>

            {selectedTrackInfo && selectedResult && (
              <div className="track-result-detail">
                <div className={`result-status-card match-${selectedStatus} ${selectedResult.is_completed ? "complete" : "incomplete"}`}>
                  <div className={`result-status-icon ${selectedResult.is_completed ? "" : "incomplete-icon"}`}>
                    {selectedResult.is_completed ? <span className="result-status-symbol">🏆</span> : <TargetStatusIcon />}
                  </div>
                  <div className="result-status-text-wrap">
                    <div className={`challenge-status-pill result-status-badge status-${getTrackBadgeTone(selectedResult)}`}>
                      {getTrackBadgeLabel(selectedResult)}
                    </div>
                    <h2 className="result-status-title">{formatTrackName(selectedResult.track_name)}</h2>
                    <div className="selected-detail-stats" aria-label="선택 트랙 요약">
                      <span>{selectedProgressPercent}% 진행</span>
                      <span>{selectedRuleSummary}</span>
                      <span>{selectedRequirementSummary}</span>
                    </div>
                    <p className="result-status-desc">{selectedStatusDescription}</p>
                  </div>
                </div>

                <div className="track-result-detail-scroll">
                  <div className="result-progress-card">
                    <div className="result-progress-header">
                      <span className="result-progress-label">현재 진행률</span>
                      <span className="result-progress-summary">
                        <strong className="result-progress-value">{selectedProgressPercent}%</strong>
                        <span className={`result-status-badge compact status-${selectedStatus === "unrelated" ? "low" : selectedResult.is_completed ? "complete" : "progress"}`}>
                          {getProgressBadgeLabel(selectedResult)}
                        </span>
                      </span>
                    </div>
                    <div className="result-progress-bar progress-runner-bar">
                      <div className="result-progress-fill" style={{ width: `${selectedProgressPercent}%` }} />
                    </div>
                  </div>

                  {selectedResult.missing_courses.length > 0 && (
                    <div className="challenge-message-box mission-card">
                      <div className="mission-card-title-row">
                        <div className="mission-title-wrap">
                          <div className="mission-card-title">
                            📌 선택 가능한 보완 과목
                          </div>
                        </div>
                        <div className="mission-card-right">
                          {!selectedResult.is_completed && selectedRequiredCourses > 0 && (
                            <span className="mission-needed-inline">최소 {selectedRequiredCourses}과목, 총 {selectedCandidateCourseCount}개</span>
                          )}
                          {selectedResult.is_completed && (
                            <span className="mission-count-inline">총 {selectedCandidateCourseCount}개</span>
                          )}
                          {selectedResult.missing_courses.length > 0 && (
                            <button
                              type="button"
                              className="mission-toggle-button"
                              onClick={() => setIsMissingCoursesExpanded(prev => !prev)}
                              aria-expanded={isMissingCoursesExpanded}
                            >
                              {isMissingCoursesExpanded ? "▲" : "▼"}
                            </button>
                          )}
                        </div>
                      </div>
                      <ul className={`mission-list ${!isMissingCoursesExpanded ? "collapsed" : ""}`}>
                        {(() => {
                          const allNoteMap = new Map<string, string>(
                            (selectedResult.rule_results || []).flatMap(r =>
                              [...(r.taken_course_details || []), ...(r.remaining_course_details || []), ...(r.missing_course_details || [])]
                                .filter(d => d.note)
                                .map(d => [d.course_name, d.note] as [string, string])
                            )
                          );
                          return (isMissingCoursesExpanded ? selectedResult.missing_courses : []).map((mc, mci) => {
                            const note = allNoteMap.get(mc);
                            const tooltipId = `mission-${selectedResult.track_id}-${mci}-${mc}`;
                            return (
                              <li key={mc} className="mission-item">
                                {mc}
                                {renderNoteIcon(tooltipId, note)}
                              </li>
                            );
                          });
                        })()}
                      </ul>
                    </div>
                  )}

                  <div className="module-detail-list">
                    {selectedDisplayRules.map((r, i) => {
                    const isAdditional = isAdditionalCheckRule(r);
                    const previousRule = selectedDisplayRules[i - 1];
                    const previousIsAdditional = previousRule ? isAdditionalCheckRule(previousRule) : false;
                    const showRuleGroupLabel =
                      i === 0 ||
                      previousIsAdditional !== isAdditional ||
                      (!isAdditional && previousRule?.satisfied !== r.satisfied);
                    const ruleGroupLabel = isAdditional ? "추가 확인" : r.satisfied ? "충족한 조건" : "추가 이수 필요";
                    const ruleGroupTone = isAdditional ? "additional" : r.satisfied ? "satisfied" : "missing";
                    const moduleKey = `${r.rule_type}-${r.description}-${r.required_value}-${i}`;
                    const isExpanded = isAdditional ? expandedAdditional.has(i) : expandedModules.has(moduleKey);
                    const isCreditRule = ['module_min_credits', 'track_min_credits'].includes(r.rule_type);
                    const current = isCreditRule
                      ? Math.max(0, r.required_value - r.shortage_credits)
                      : (r.current_value ?? 0);
                    const ruleUnit = isCreditRule ? '학점' : '과목';
                    const remainingCourses = Array.from(new Set([
                      ...((r.remaining_courses || []) as string[]),
                      ...(r.satisfied ? [] : (r.missing_courses || [])),
                    ])).filter(c => !(r.taken_courses || []).includes(c));
                    const hasCourses = !isAdditional && ((r.taken_courses && r.taken_courses.length > 0) || remainingCourses.length > 0);
                    const ruleNoteMap = new Map<string, string>(
                      [...(r.taken_course_details || []), ...(r.remaining_course_details || []), ...(r.missing_course_details || [])]
                        .filter(d => d.note)
                        .map(d => [d.course_name, d.note])
                    );
                    const helpText = isAdditional ? getAdditionalCheckHelp(r, selectedResult.dept_name, selectedResult.track_name) : null;
                    const toggleExpand = () => {
                      if (isAdditional) {
                        setExpandedAdditional(prev => { const next = new Set(prev); if (next.has(i)) next.delete(i); else next.add(i); return next; });
                      } else {
                        if (!hasCourses) return;
                        setExpandedModules(prev => { const next = new Set(prev); if (next.has(moduleKey)) next.delete(moduleKey); else next.add(moduleKey); return next; });
                      }
                    };
                    return (
                      <React.Fragment key={moduleKey}>
                        {showRuleGroupLabel && (
                          <div className={`module-rule-group-label ${ruleGroupTone}`}>
                            {ruleGroupLabel}
                          </div>
                        )}
                      <div className={`module-detail-item ${r.satisfied ? 'satisfied' : 'unsatisfied'}${isAdditional ? ' additional-check-row' : ''}`}>
                        <div
                          className="module-detail-header"
                          onClick={toggleExpand}
                          style={{ cursor: (hasCourses || isAdditional) ? 'pointer' : 'default' }}
                        >
                          <span className={`module-status-icon ${isAdditional ? 'additional' : (r.satisfied ? 'good' : 'warn')}`}>
                            {isAdditional ? '!' : (r.satisfied ? '✓' : '✗')}
                          </span>
                          <span className="module-desc">
                            {isAdditional ? getAdditionalCheckLabel(r, selectedResult.dept_name, selectedResult.track_name) : formatRuleDescription(r.description)}
                          </span>
                          {!isAdditional && (
                            <span className="module-credit-badge" style={{ color: current >= r.required_value ? '#0d9467' : '#c44a6a' }}>
                              {current}/{r.required_value}{ruleUnit}
                            </span>
                          )}
                          {(hasCourses || isAdditional) && (
                            <span className="module-expand-icon">{isExpanded ? '▲' : '▼'}</span>
                          )}
                        </div>
                        {isExpanded && !isAdditional && hasCourses && (
                          <div className="module-course-chips">
                            {r.taken_courses && r.taken_courses.map((c, ci) => {
                              const note = ruleNoteMap.get(c) || moduleCourses.find(x => x.name === c)?.note;
                              const tooltipId = `taken-${r.description}-${ci}-${c}`;
                              return (
                                <span key={`t-${ci}`} className="course-chip taken">
                                  {c}
                                  {note && (
                                    <span
                                      className={`chip-note-wrap ${activeMobileTooltip === tooltipId ? "tooltip-open" : ""}`}
                                      role="button"
                                      tabIndex={0}
                                      onClick={(event) => toggleMobileTooltip(tooltipId, event)}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter" || event.key === " ") toggleMobileTooltip(tooltipId, event);
                                      }}
                                    >
                                      ⚠️<span className="chip-note-tooltip">{note}</span>
                                    </span>
                                  )}
                                </span>
                              );
                            })}
                            {remainingCourses.map((c, ci) => {
                              const note = ruleNoteMap.get(c) || moduleCourses.find(x => x.name === c)?.note;
                              const tooltipId = `remaining-${r.description}-${ci}-${c}`;
                              return (
                                <span key={`m-${ci}`} className={`course-chip ${r.satisfied ? "remaining" : "missing"}`}>
                                  {c}
                                  {note && (
                                    <span
                                      className={`chip-note-wrap ${activeMobileTooltip === tooltipId ? "tooltip-open" : ""}`}
                                      role="button"
                                      tabIndex={0}
                                      onClick={(event) => toggleMobileTooltip(tooltipId, event)}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter" || event.key === " ") toggleMobileTooltip(tooltipId, event);
                                      }}
                                    >
                                      ⚠️<span className="chip-note-tooltip">{note}</span>
                                    </span>
                                  )}
                                </span>
                              );
                            })}
                          </div>
                        )}
                        {isExpanded && isAdditional && helpText && (
                          <div className="module-additional-help">
                            {helpText.replace(/\n{2,}/g, '\n')}
                          </div>
                        )}
                      </div>
                      </React.Fragment>
                    );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="manual-button-group">
            <button className="sub-button" onClick={() => setPage("trackList")}>이전 단계</button>
            <button className="button" onClick={() => setShowResetConfirm(true)}>
              처음으로
            </button>
          </div>
        </div>
      )}

      {floatingTooltip && (
        <div
          className="floating-note-tooltip"
          style={{ left: floatingTooltip.x, top: floatingTooltip.y }}
        >
          {floatingTooltip.text}
        </div>
      )}

      {showResetConfirm && (
        <div className="modal-overlay" onClick={() => setShowResetConfirm(false)}>
          <div className="modal reset-confirm-modal" onClick={e => e.stopPropagation()}>
            <h2 className="reset-confirm-title">처음으로 돌아갈까요?</h2>
            <p className="reset-confirm-desc">
              입력한 과목 정보와 분석 결과가 모두 초기화됩니다.<br />
              계속하시겠습니까?
            </p>
            <div className="reset-confirm-actions">
              <button
                className="reset-cancel-btn"
                onClick={() => setShowResetConfirm(false)}
              >
                취소
              </button>
              <button
                className="reset-ok-btn"
                onClick={() => {
                  setShowResetConfirm(false);
                  setSelectedMajors([]);
                  setMajorDraft("");
                  setCourses([{ id: 1, name: "", credit: "3", grade: "이수" }]);
                  setDeptAnalyses([]);
                  setSelectedTrackId(null);
                  setExpandedResultGroups({ close: false, review: false, unrelated: false });
                  setExpandedModules(new Set());
                  setExpandedAdditional(new Set());
                  setModuleCourses([]);
                  setSelectedDeptTracks([]);
                  setCheckedCourseNames(new Set());
                  setChecklistDeptFilter(null);
                  setTrackExploreDeptFilter(null);
                  setSelectedExploreTrackId(null);
                  setAllDeptCourses([]);
                  allCourseCreditsRef.current.clear();
                  setShowCourseInfoTip(false);
                  setShowTrackInfoTip(false);
                  setActiveMobileTooltip(null);
                  setMajorLimitMessage("");
                  setPreviousTrackPage("checklist");
                  setMaxReachedStep(1);
                  setPage("info");
                }}
              >
                처음으로
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AppWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

export default AppWithErrorBoundary;
