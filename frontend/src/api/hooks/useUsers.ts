import { useState, useCallback } from 'react';
import { api } from '../api';

export interface User {
  id: number;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  roles: string[];
}

export interface Role {
  id: number;
  name: string;
  permissions: string[];
}

export const useUsers = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get('/users');
      if (!Array.isArray(response.data)) {
        throw new Error('Received invalid data format from server (expected array)');
      }
      setUsers(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch users');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchRoles = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get('/roles');
      if (!Array.isArray(response.data)) {
        throw new Error('Received invalid data format from server (expected array)');
      }
      setRoles(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch roles');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createUser = async (email: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      await api.post('/users', { email, password });
      await fetchUsers();
      return true;
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create user');
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const assignRole = async (userId: number, roleName: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      await api.put(`/users/${userId}/role`, { role_name: roleName });
      await fetchUsers();
      return true;
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to assign role');
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  return { users, roles, isLoading, error, fetchUsers, fetchRoles, createUser, assignRole };
};
