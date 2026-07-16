import { createRouter, createWebHistory } from 'vue-router';
import WorkspaceView from '../views/WorkspaceView.vue';
import CopyLibraryView from '../views/CopyLibraryView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'workspace',
      component: WorkspaceView,
    },
    {
      path: '/copywriting',
      name: 'copywriting',
      component: CopyLibraryView,
    },
  ],
  scrollBehavior() {
    return { top: 0 };
  },
});

export default router;
