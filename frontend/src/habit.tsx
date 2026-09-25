import { useState } from 'react';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Modal from 'react-bootstrap/Modal';
import Table from 'react-bootstrap/Table';

import './habit.css';

type HabitKeyword = {
  id: number;
  isPublic: boolean;
  keyword: string;
};

const createKeyword = (id: number): HabitKeyword => ({
  id,
  isPublic: false,
  keyword: '',
});

function Habit() {
  const [keywords, setKeywords] = useState<HabitKeyword[]>([createKeyword(1)]);
  const [nextId, setNextId] = useState(2);
  const [deleteTarget, setDeleteTarget] = useState<HabitKeyword | null>(null);

  const updateKeyword = (
    id: number,
    update: Partial<Omit<HabitKeyword, 'id'>>,
  ) => {
    setKeywords((currentKeywords) =>
      currentKeywords.map((habitKeyword) =>
        habitKeyword.id === id ? { ...habitKeyword, ...update } : habitKeyword,
      ),
    );
  };

  const addKeyword = () => {
    setKeywords((currentKeywords) => [...currentKeywords, createKeyword(nextId)]);
    setNextId((currentId) => currentId + 1);
  };

  const deleteKeyword = (id: number) => {
    setKeywords((currentKeywords) =>
      currentKeywords.filter((habitKeyword) => habitKeyword.id !== id),
    );
    setDeleteTarget(null);
  };

  return (
    <section className="habit-settings" aria-labelledby="habit-settings-title">

      <div className="habit-settings__table-wrap">
        <Table className="habit-settings__table" responsive>
          <thead>
            <tr>
              <th scope="col" className="habit-settings__public-column">
                公開
              </th>
              <th scope="col" className="habit-settings__continued-column">
                続いた日時
              </th>
              <th scope="col">キーワード</th>
              <th scope="col" className="habit-settings__delete-column">
                <span className="visually-hidden">削除</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {keywords.map((habitKeyword) => (
              <tr key={habitKeyword.id}>
                <td className="habit-settings__public-cell">
                  <Form.Check
                    type="checkbox"
                    id={`habit-public-${habitKeyword.id}`}
                    checked={habitKeyword.isPublic}
                    onChange={(event) =>
                      updateKeyword(habitKeyword.id, {
                        isPublic: event.target.checked,
                      })
                    }
                    aria-label="この習慣を公開する"
                  />
                </td>
                <td className="habit-settings__continued-cell">
                  <span className="habit-settings__not-recorded">未計測</span>
                </td>
                <td>
                  <Form.Control
                    type="text"
                    value={habitKeyword.keyword}
                    onChange={(event) =>
                      updateKeyword(habitKeyword.id, {
                        keyword: event.target.value,
                      })
                    }
                    placeholder="例：読書"
                    aria-label="キーワード"
                  />
                </td>
                <td className="habit-settings__delete-cell">
                  <Button
                    variant="link"
                    className="habit-settings__delete-button"
                    onClick={() => setDeleteTarget(habitKeyword)}
                    aria-label="キーワードを削除する"
                  >
                    削除
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>

        {keywords.length === 0 && (
          <p className="habit-settings__empty">キーワードが登録されていません。</p>
        )}
      </div>

      <div className="habit-settings__actions">
        <Button variant="primary" onClick={addKeyword}>
          +
        </Button>
      </div>

      <Modal
        show={deleteTarget !== null}
        onHide={() => setDeleteTarget(null)}
        centered
        aria-labelledby="delete-habit-keyword-title"
      >
        <Modal.Header closeButton>
          <Modal.Title id="delete-habit-keyword-title">
            キーワードを削除しますか？
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {deleteTarget?.keyword ? (
            <>「{deleteTarget.keyword}」を削除すると、元に戻せません。</>
          ) : (
            'このキーワードを削除すると、元に戻せません。'
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
            キャンセル
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (deleteTarget !== null) {
                deleteKeyword(deleteTarget.id);
              }
            }}
          >
            削除する
          </Button>
        </Modal.Footer>
      </Modal>
    </section>
  );
}

export default Habit;
