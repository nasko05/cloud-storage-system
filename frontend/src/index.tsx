import React from 'react';
import ReactDOM from 'react-dom/client';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import App from './App';

const theme = createTheme({
  palette: {
    primary: { main: '#1E40AF' },
    secondary: { main: '#0F766E' },
    background: { default: '#F8FAFC' }
  },
  shape: {
    borderRadius: 12
  },
  typography: {
    fontFamily: '"Work Sans", "Helvetica", "Arial", sans-serif'
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
