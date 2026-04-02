import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from "react-router-dom"
import React from "react"
import './index.css'
import App from './App.tsx'
import * as login_app from './login/App.tsx'
import { CookiesProvider } from "react-cookie";

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CookiesProvider>

    <BrowserRouter>
	  <Routes>
		<Route path="/" element={<App />} />
		<Route path="/login" element={<login_app.default />} />
	  </Routes>
	</BrowserRouter>
  </CookiesProvider>
  </StrictMode>,
)
