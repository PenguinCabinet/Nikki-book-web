import { useState } from 'react'
import { Button } from 'react-bootstrap';
import Form from 'react-bootstrap/Form';
import { useNavigate } from 'react-router-dom';

function App() {
    const navigate = useNavigate();

    const handleSubmit=(e: React.FormEvent<HTMLFormElement>)=>{

        e.preventDefault();
    
        const formData = new FormData(e.currentTarget);     
        
        fetch(`${import.meta.env.VITE_BACKEND_ORIGIN}/token`, {
            method: 'POST',
            body: formData,
            credentials: 'include',
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`http error: ${response.status}`);
            }
            return response.json();
        })
        .then((data)=>{
          navigate('/');
        })
    }

  return (
    <>
    <Form onSubmit={handleSubmit}>
      <p>
        <Form.Text id="passwordHelpBlock" >
          login
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
      <Button type='submit'>login</Button>
    </Form>
    </>
  )
}

export default App
