import React from 'react';
import ReactDOM from 'react-dom/client';
import { alpha, createTheme, ThemeProvider } from '@mui/material/styles';
import App from './App';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';

// Design tokens: an indigo-anchored palette on a cool neutral canvas, soft
// shadows instead of hard borders, and sentence-case typography throughout.
const INDIGO = '#4F46E5';
const INK = '#1C2130';

const theme = createTheme({
  palette: {
    primary: { main: INDIGO, dark: '#4338CA', light: '#818CF8' },
    secondary: { main: '#0EA5E9' },
    background: { default: '#F4F5FA', paper: '#FFFFFF' },
    text: { primary: INK, secondary: '#5D6474' },
    divider: alpha(INK, 0.08),
    error: { main: '#DC2626' },
    warning: { main: '#D97706' },
    info: { main: '#0284C7' },
    success: { main: '#16A34A' },
    action: {
      hover: alpha(INDIGO, 0.05),
      selected: alpha(INDIGO, 0.1),
      focus: alpha(INDIGO, 0.12)
    }
  },
  shape: {
    borderRadius: 10
  },
  typography: {
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    h5: { fontWeight: 700, letterSpacing: '-0.02em' },
    h6: { fontWeight: 700, letterSpacing: '-0.01em' },
    subtitle1: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 }
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 9, paddingInline: 14 },
        outlined: { borderColor: alpha(INK, 0.16) }
      }
    },
    MuiIconButton: {
      styleOverrides: { root: { borderRadius: 9 } }
    },
    MuiPaper: {
      styleOverrides: { rounded: { borderRadius: 14 } }
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 14 } }
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 18,
          boxShadow: '0 24px 64px rgba(18, 22, 39, 0.22)'
        }
      }
    },
    MuiDialogTitle: {
      styleOverrides: { root: { fontWeight: 700 } }
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          boxShadow: '0 12px 32px rgba(18, 22, 39, 0.14)',
          border: `1px solid ${alpha(INK, 0.06)}`
        }
      }
    },
    MuiMenuItem: {
      styleOverrides: { root: { borderRadius: 8, marginInline: 4 } }
    },
    MuiListItemButton: {
      styleOverrides: { root: { borderRadius: 9 } }
    },
    MuiChip: {
      styleOverrides: { root: { borderRadius: 8, fontWeight: 500 } }
    },
    MuiToggleButtonGroup: {
      styleOverrides: {
        root: {
          backgroundColor: alpha(INK, 0.045),
          borderRadius: 10,
          padding: 3,
          gap: 2
        }
      }
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          border: 'none',
          borderRadius: '8px !important',
          paddingBlock: 4,
          paddingInline: 10,
          '&.Mui-selected': {
            backgroundColor: '#FFFFFF',
            boxShadow: '0 1px 4px rgba(18, 22, 39, 0.12)',
            '&:hover': { backgroundColor: '#FFFFFF' }
          }
        }
      }
    },
    MuiTab: {
      styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } }
    },
    MuiTooltip: {
      defaultProps: { arrow: true },
      styleOverrides: { tooltip: { borderRadius: 8, fontSize: '0.75rem' } }
    },
    MuiAlert: {
      styleOverrides: { root: { borderRadius: 12 } }
    },
    MuiTextField: {
      defaultProps: { size: 'small' }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { borderRadius: 10 },
        notchedOutline: { borderColor: alpha(INK, 0.16) }
      }
    }
  }
});

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found');
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
