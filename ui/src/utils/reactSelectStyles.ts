import type {StylesConfig, ThemeConfig} from 'react-select'

// Shared react-select styles that respect the app CSS variables and dark mode
export const selectStyles: StylesConfig<any, boolean> = {
  control: (base, state) => ({
    ...base,
    backgroundColor: 'var(--bg)',
    color: 'var(--text)',
    borderColor: state.isFocused ? '#60a5fa' : 'rgba(148, 163, 184, 0.4)', // slate-400/40
    boxShadow: 'none',
    ':hover': { borderColor: '#60a5fa' },
    minHeight: 38,
  }),
  valueContainer: (base) => ({
    ...base,
    color: 'var(--text)'
  }),
  menu: (base) => ({
    ...base,
    backgroundColor: 'var(--bg)',
    color: 'var(--text)',
    zIndex: 5,
  }),
  menuList: (base) => ({
    ...base,
    backgroundColor: 'var(--bg)'
  }),
  option: (base, state) => ({
    ...base,
    backgroundColor: state.isSelected
      ? '#0ea5e9' // sky-500
      : state.isFocused
        ? 'rgba(14, 165, 233, 0.18)'
        : 'transparent',
    color: state.isSelected ? '#ffffff' : 'var(--text)',
    ':active': {
      backgroundColor: state.isSelected ? '#0ea5e9' : 'rgba(14, 165, 233, 0.26)'
    }
  }),
  input: (base) => ({
    ...base,
    color: 'var(--text)'
  }),
  singleValue: (base) => ({
    ...base,
    color: 'var(--text)'
  }),
  placeholder: (base) => ({
    ...base,
    color: 'var(--muted)'
  }),
  multiValue: (base) => ({
    ...base,
    backgroundColor: 'rgba(14, 165, 233, 0.15)'
  }),
  multiValueLabel: (base) => ({
    ...base,
    color: 'var(--text)'
  }),
  multiValueRemove: (base) => ({
    ...base,
    color: 'var(--text)',
    ':hover': { backgroundColor: 'rgba(14, 165, 233, 0.25)', color: 'var(--text)' }
  }),
  dropdownIndicator: (base) => ({
    ...base,
    color: 'var(--muted)'
  }),
  clearIndicator: (base) => ({
    ...base,
    color: 'var(--muted)'
  }),
  indicatorSeparator: (base) => ({
    ...base,
    backgroundColor: 'rgba(148, 163, 184, 0.4)'
  }),
}

export const selectTheme: ThemeConfig = (theme) => ({
  ...theme,
  colors: {
    ...theme.colors,
    primary: '#0ea5e9', // sky-500
    primary75: '#38bdf8',
    primary50: 'rgba(14, 165, 233, 0.5)',
    primary25: 'rgba(14, 165, 233, 0.25)',
    neutral0: 'var(--bg)',
    neutral5: 'var(--bg)',
    neutral10: 'var(--bg)',
    neutral20: 'rgba(148, 163, 184, 0.4)',
    neutral30: '#60a5fa',
    neutral40: 'var(--muted)',
    neutral50: 'var(--muted)',
    neutral60: 'var(--muted)',
    neutral70: 'var(--muted)',
    neutral80: 'var(--text)',
    neutral90: 'var(--text)'
  },
  borderRadius: 6,
})
