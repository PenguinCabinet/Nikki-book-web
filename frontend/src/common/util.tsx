import { useCookies } from "react-cookie";
import type { NavigateFunction } from 'react-router-dom';

export async function fetch_with_login(path:string,fetch_init:any,navigate:NavigateFunction,cookies:any,Content_Type:string='application/json'){

    if(cookies.token===undefined){
        navigate('/login');
    }

    const result=(await fetch(
        `${import.meta.env.VITE_BACKEND_ORIGIN}${path}`,
        fetch_init
    ));
    
    if(result.status!=200){
        navigate('/login');
    }

    return await result.json()
}