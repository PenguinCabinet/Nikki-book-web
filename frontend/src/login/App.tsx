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
    
        const formData = new FormData(e.target);     
        
        fetch('http://127.0.0.1:8000/token', {
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
      <Form.Text id="passwordHelpBlock" >
        login
      </Form.Text>

      <Form.Label htmlFor="username">Username</Form.Label>
      <Form.Control
        type="input"
        name="username"
      />

      <Form.Label htmlFor="password">Password</Form.Label>
      <Form.Control
        type="password"
        name="password"
        aria-describedby="passwordHelpBlock"
      />
      <Button type='submit'>submit</Button>
    </Form>
    </>
  )
}

export default App
