import { useState } from 'react'
import { Button } from 'react-bootstrap';
import Form from 'react-bootstrap/Form';
import { useCookies } from "react-cookie";
import { useNavigate } from 'react-router-dom';

function App() {
    const [cookies, setCookie, removeCookie] = useCookies(["token"]);
    const navigate = useNavigate();

    const handleSubmit=(e: React.FormEvent<HTMLFormElement>)=>{

        e.preventDefault();
    
        const formData = new FormData(e.currentTarget);     
        
        fetch(`${import.meta.env.VITE_BACKEND_ORIGIN}/register`, {
            method: 'POST',
            body: formData,
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`http error: ${response.status}`);
            }
            return response.json();
        })
        .then((data)=>{
          setCookie("token", data);
          navigate('/');
        })
    }

  return (
    <>
    <Form onSubmit={handleSubmit}>
      <p>
        <Form.Text id="passwordHelpBlock" >
          register
        </Form.Text>
      </p>

      <Form.Label name="username" htmlFor="username">Username</Form.Label>
      <Form.Control
        type="input"
        id="username"
        name="username"
 	autoComplete="username" required={true}
      />

      <Form.Label name="password" htmlFor="username">Password</Form.Label>
      <Form.Control
        type="password"
        id="password"
        name="password"
        aria-describedby="passwordHelpBlock"
 	autoComplete="current-password" required={true}
      />
      <Button type='submit'>register</Button>

    </Form>
    </>
  )
}

export default App
