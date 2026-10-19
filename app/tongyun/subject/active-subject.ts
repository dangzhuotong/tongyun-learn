// tongyun: 当前学科。layout / SubjectSwitch 只从这里取（不直接引 bank / 题库）。
// 实现统一在 ui-subject：同一 localStorage key + tongyun-subject-changed，含英语。
export {
  STORAGE_KEY,
  UI_SUBJECTS,
  getActiveSubject,
  setActiveSubject,
  useActiveSubject,
  __resetActiveSubject,
  isBankSubject,
  type ActiveSubject,
  type UiSubject,
  type UseActiveSubject,
} from './ui-subject'
