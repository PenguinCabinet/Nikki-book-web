import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from "react-router-dom"
import React from "react"
import './index.css'
import App from './App.tsx'
import * as login_app from './login/App.tsx'
import * as register from './register/App.tsx'
import * as zip_upload from './zip-upload/App.tsx'
import { CookiesProvider } from "react-cookie";

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CookiesProvider>

    <BrowserRouter>
	  <Routes>
		<Route path="/" element={<App />} />
		<Route path="/login" element={<login_app.default />} />
		<Route path="/register" element={<register.default />} />
		<Route path="/zip-upload" element={<zip_upload.default />} />
	  </Routes>
	</BrowserRouter>
  </CookiesProvider>
  </StrictMode>,
)
