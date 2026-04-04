import { useCookies } from "react-cookie";
import type { NavigateFunction } from 'react-router-dom';

export async function fetch_with_login(path:string,method:string,body:any,navigate:NavigateFunction,cookies:any){

    if(cookies.token===undefined){
        navigate('/login');
    }

    const result=(await fetch(
        `${import.meta.env.VITE_BACKEND_ORIGIN}${path}`,
        method=="GET"?
        {
          method: method,
          headers: {
            'Authorization': 'Bearer '+cookies.token.access_token,
            'Content-Type': 'application/json',
          }
        }:
        {
          method: method,
          body: JSON.stringify(body),
          headers: {
            'Authorization': 'Bearer '+cookies.token.access_token,
            'Content-Type': 'application/json',
          }
        }
    ));
    console.log(result.status)
    if(result.status!=200){
        navigate('/login');
    }

    return await result.json()
}