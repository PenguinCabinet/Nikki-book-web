import { useCookies } from "react-cookie";
import type { NavigateFunction } from 'react-router-dom';

export async function fetch_with_login(path:string,fetch_init:any,navigate:NavigateFunction,Content_Type:string='application/json'){

    const result=(await fetch(
        `${import.meta.env.VITE_BACKEND_ORIGIN}${path}`,
        {
            ...fetch_init,
            credentials: 'include',
        }
    ));
    
    if(result.status===401){
        navigate('/login');
    }

    if(!result.ok){
        return null;
    }

    return await result.json()
}