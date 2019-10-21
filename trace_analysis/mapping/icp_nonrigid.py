import numpy as np
from sklearn.neighbors import NearestNeighbors
from trace_analysis.image_adapt.polywarp import polywarp, polywarp_apply
import cv2
from trace_analysis.coordinate_transformations import transform

def best_fit_transform(A, B):
    '''
    Calculates the least-squares best-fit transform that maps corresponding points A to B in m spatial dimensions
    Input:
      A: Nxm numpy array of corresponding points
      B: Nxm numpy array of corresponding points
    Returns:
      T: (m+1)x(m+1) homogeneous transformation matrix that maps A on to B
      R: mxm rotation matrix
      t: mx1 translation vector
    '''

    assert A.shape == B.shape

    # get number of dimensions
    m = A.shape[1]

    # translate points to their centroids
    centroid_A = np.mean(A, axis=0)
    centroid_B = np.mean(B, axis=0)
    AA = A - centroid_A
    BB = B - centroid_B

    # rotation matrix
    H = np.dot(AA.T, BB)
    U, S, Vt = np.linalg.svd(H)
    R = np.dot(Vt.T, U.T)

    # special reflection case
    if np.linalg.det(R) < 0:
       Vt[m-1,:] *= -1
       R = np.dot(Vt.T, U.T)

    # translation
    t = centroid_B.T - np.dot(R,centroid_A.T)

    # homogeneous transformation
    T = np.identity(m+1)
    T[:m, :m] = R
    T[:m, m] = t

    return T, R, t


def nearest_neighbor(src, dst):
    '''
    Find the nearest (Euclidean) neighbor in dst for each point in src
    Input:
        src: Nxm array of points
        dst: Nxm array of points
    Output:
        distances: Euclidean distances of the nearest neighbor
        indices: dst indices of the nearest neighbor
    '''

    #assert src.shape == dst.shape

    neigh = NearestNeighbors(n_neighbors=1)
    neigh.fit(dst)
    distances, indices = neigh.kneighbors(src, return_distance=True)
    return distances.ravel(), indices.ravel()


def icp_nonrigid(A, B, init_pose=None, max_iterations=50, tolerance=0.001):
    '''
    The Iterative Closest Point method: finds best-fit transform that maps points A on to points B
    Input:
        A: Nxm numpy array of source mD points
        B: Nxm numpy array of destination mD point
        init_pose: (m+1)x(m+1) homogeneous transformation
        max_iterations: exit algorithm after max_iterations
        tolerance: convergence criteria
    Output:
        T: final homogeneous transformation that maps A on to B
        distances: Euclidean distances (errors) of the nearest neighbor
        i: number of iterations to converge
    '''

    #assert A.shape == B.shape

    # get number of dimensions
    m = A.shape[1]

    # make points homogeneous, copy them to maintain the originals
    src = np.ones((m+1,A.shape[0]))
    dst = np.ones((m+1,B.shape[0]))
    src[:m,:] = np.copy(A.T)
    dst[:m,:] = np.copy(B.T)

    # apply the initial pose estimation
    if init_pose is not None:
        src = np.dot(init_pose, src)

    prev_error = 0

    #T_final = np.identity(3)

    for i in range(max_iterations):
        # find the nearest neighbors between the current source and destination points
        distances, indices = nearest_neighbor(src[:m,:].T, dst[:m,:].T)

        # compute the transformation between the current source and nearest destination points
        T,_,_ = best_fit_transform(src[:m,:].T, dst[:m,indices].T)
        #kx, ky = polywarp(src[0,:].T,src[1,:].T,dst[0,indices].T,dst[1,indices].T)

        # update the current source
        src = np.dot(T, src)
        #src = polywarp_apply(kx, ky, src)

        #T_final = T @ T_final

        # check error
        mean_error = np.mean(distances)
        print(np.abs(prev_error - mean_error))
        #if np.abs(prev_error - mean_error) < tolerance:
            #break
        prev_error = mean_error
        print(prev_error)

    # for i in range(max_iterations):
    #     print(i)
    #     # find the nearest neighbors between the current source and destination points
    #     distances, indices = nearest_neighbor(src[:m,:].T, dst[:m,:].T)
    #
    #     # compute the transformation between the current source and nearest destination points
    #     #T,_,_ = best_fit_transform(src[:m,:].T, dst[:m,indices].T)
    #     kx, ky = polywarp( dst[0,indices].T,dst[1,indices].T, src[0,:].T,src[1,:].T, degree=4)
    #
    #     # update the current source
    #     #src = np.dot(T, src)
    #     src = polywarp_apply(kx, ky, src.T).T
    #     # check error
    #     mean_error = np.mean(distances)
    #     print(np.abs(prev_error - mean_error))
    #     #if np.abs(prev_error - mean_error) < tolerance:
    #         #break
    #     prev_error = mean_error
    #
    #     print(prev_error)

    for i in range(max_iterations):
        print(i)
        # find the nearest neighbors between the current source and destination points
        distances, indices = nearest_neighbor(src[:m, :].T, dst[:m, :].T)

        # compute the transformation between the current source and nearest destination points
        # T,_,_ = best_fit_transform(src[:m,:].T, dst[:m,indices].T)
        # kx, ky = polywarp(dst[0, indices].T, dst[1, indices].T, src[0, :].T, src[1, :].T, degree=4)
        T, mask = cv2.findHomography(src[:m,:].T, dst[:m,indices].T, cv2.RANSAC, 5.0)

        # update the current source
        # src = np.dot(T, src)
        #src = polywarp_apply(kx, ky, src.T).T
        # src = cv2.perspectiveTransform([src[:m,:]].T, T).T
        src = transform(src[:m,:].T,T).T

        #T_final = T @ T_final

        # check error
        mean_error = np.mean(distances)
        print(np.abs(prev_error - mean_error))
        # if np.abs(prev_error - mean_error) < tolerance:
        # break
        prev_error = mean_error

        print(prev_error)


    # calculate final transformation
    #T,_,_ = best_fit_transform(A, src[:m,:].T)
    # kx, ky = polywarp(src[0, :].T, src[1, :].T,  A[:,0], A[:,1],   degree = 4)
    T, mask = cv2.findHomography(A, src[:m, :].T, cv2.RANSAC, 5.0)
    # print('degree is 4')

    return T, distances, i
